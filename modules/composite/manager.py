import asyncio
from asyncio import Semaphore
from typing import Dict

from config import logger
from .ast_transform import Expr
from .composite_listener import CompositeListener
from .utils import ast_to_string


class CompositeListenerManager:
    """Singleton‑менеджер CompositeListener‑ов.

    Управляет композитными слушателями алертов, обеспечивает создание, 
    удаление и подписку пользователей. Использует динамический семафор 
    для контроля параллельности и пакетную обработку для масштабирования.

    Attributes:
        _instance: Единственный экземпляр менеджера (Singleton).
        _listeners: Словарь слушателей по ID условий.
        _current_semaphore_size: Текущий размер семафора.
        semaphore: Семафор для ограничения параллельности.
    """

    _instance: "CompositeListenerManager | None" = None

    def __init__(self) -> None:
        """Инициализирует менеджер композитных слушателей.
        
        Создает пустой словарь слушателей, устанавливает начальный размер
        семафора равным 50 и инициализирует семафор.
        """
        self._listeners: Dict[str, CompositeListener] = {}
        self._current_semaphore_size = 50
        self.semaphore = Semaphore(self._current_semaphore_size)

    @classmethod
    def instance(cls) -> "CompositeListenerManager":
        """Возвращает единственный экземпляр менеджера.

        Реализует паттерн Singleton, создавая экземпляр при первом вызове
        и возвращая его при последующих вызовах.

        Returns:
            CompositeListenerManager: Единственный экземпляр менеджера.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _generate_condition_id(self, expr: Expr) -> str:
        """Генерирует уникальный детерминированный ID для композитного условия.

        Создает хеш от строкового представления AST выражения для получения
        уникального идентификатора условия алерта.

        Args:
            expr: AST выражение условия алерта.

        Returns:
            str: Строковый идентификатор (числовой хеш).
        """
        expr_string = ast_to_string(expr)
        return str(hash(expr_string))

    def _update_semaphore_if_needed(self) -> None:
        """Обновляет размер семафора на основе текущего количества слушателей.
        
        Вычисляет оптимальный размер семафора (1 на каждые 40 алертов, минимум 50,
        максимум 500) и обновляет семафор только если размер изменился более чем на 20%.
        """
        listeners_count = len(self._listeners)
        
        optimal_size = min(500, max(50, listeners_count // 40))
        
        if abs(optimal_size - self._current_semaphore_size) > self._current_semaphore_size * 0.2:
            logger.info(
                f"[SEMAPHORE] Обновляем размер семафора: {self._current_semaphore_size} → {optimal_size} "
                f"(алертов: {listeners_count})"
            )
            self._current_semaphore_size = optimal_size
            self.semaphore = Semaphore(optimal_size)

    async def add_listener(self, expr: Expr, user_id: int) -> CompositeListener:
        """Создаёт новый или подписывает на существующий композитный слушатель.

        Если слушатель с таким условием уже существует, пользователь подписывается
        на него. В противном случае создаётся новый слушатель с этим пользователем
        в качестве первого подписчика.

        Args:
            expr: Корневое AST выражение условия алерта.
            user_id: Telegram ID владельца/подписчика алерта.

        Returns:
            CompositeListener: Слушатель (новый или существующий).

        Raises:
            Exception: При ошибке создания или запуска нового слушателя.
        """
        condition_id = self._generate_condition_id(expr)
        
        if condition_id in self._listeners:
            existing_listener = self._listeners[condition_id]
            existing_listener.add_subscriber(user_id)
            logger.info(f"[COMPOSITE] Подписка пользователя {user_id} на существующий слушатель {condition_id}")
            return existing_listener
        else:
            listener = CompositeListener(expr, user_id, condition_id)
            await listener.start()
            self._listeners[condition_id] = listener
            logger.info(f"[COMPOSITE] Создан новый слушатель {condition_id} для пользователя {user_id}")
            
            # Обновляем семафор после добавления нового слушателя
            self._update_semaphore_if_needed()
            
            return listener
        
    async def remove_listener(self, condition_id: str) -> bool:
        """Удаляет слушатель по ID условия.

        Останавливает работу слушателя и удаляет его из менеджера.
        Обновляет размер семафора после удаления.

        Args:
            condition_id: ID условия слушателя для удаления.

        Returns:
            bool: True если слушатель был удалён, False если не найден.

        Raises:
            Exception: При ошибке остановки слушателя (логируется, не прерывает выполнение).
        """
        if condition_id not in self._listeners:
            logger.warning(f"[COMPOSITE] Слушатель {condition_id} не найден для удаления")
            return False
        
        listener = self._listeners[condition_id]
        try:
            await listener.stop()
        except Exception as exc:
            logger.exception(f"[COMPOSITE] Ошибка при остановке композитного слушателя: {exc}")
        
        del self._listeners[condition_id]
        logger.info(f"[COMPOSITE] Слушатель {condition_id} удалён")
        
        # Обновляем семафор после удаления слушателя
        self._update_semaphore_if_needed()
        
        return True

    async def unsubscribe_user(self, condition_id: str, user_id: int) -> bool:
        """Отписывает пользователя от слушателя.

        Удаляет пользователя из списка подписчиков слушателя.
        Если после отписки в слушателе не остаётся подписчиков,
        слушатель автоматически удаляется.

        Args:
            condition_id: ID условия слушателя.
            user_id: Telegram ID пользователя для отписки.

        Returns:
            bool: True если пользователь был отписан, False если слушатель не найден
                или пользователь не был подписан.

        Raises:
            Exception: При ошибке удаления слушателя (логируется, не прерывает выполнение).
        """
        if condition_id not in self._listeners:
            logger.warning(f"[COMPOSITE] Слушатель {condition_id} не найден для отписки пользователя {user_id}")
            return False
        
        listener = self._listeners[condition_id]
        
        if user_id not in listener.subscribers:
            logger.warning(f"[COMPOSITE] Пользователь {user_id} не подписан на слушатель {condition_id}")
            return False
        
        listener.remove_subscriber(user_id)
        logger.info(f"[COMPOSITE] Пользователь {user_id} отписан от слушателя {condition_id}")
        
        if not listener.subscribers:
            logger.info(f"[COMPOSITE] Слушатель {condition_id} не имеет подписчиков, удаляем")
            await self.remove_listener(condition_id)
        
        return True

    async def remove_user_from_all_listeners(self, user_id: int) -> int:
        """Отписывает пользователя от всех слушателей.

        Проходит по всем слушателям и удаляет указанного пользователя
        из их списков подписчиков. Слушатели без подписчиков удаляются.

        Args:
            user_id: Telegram ID пользователя для отписки.

        Returns:
            int: Количество слушателей, от которых пользователь был отписан.

        Raises:
            Exception: При ошибке удаления слушателей (логируется, не прерывает выполнение).
        """
        removed_count = 0
        listeners_to_remove = []
        
        for condition_id, listener in self._listeners.items():
            if user_id in listener.subscribers:
                listener.remove_subscriber(user_id)
                removed_count += 1
                logger.info(f"[COMPOSITE] Пользователь {user_id} отписан от слушателя {condition_id}")
                
                if not listener.subscribers:
                    listeners_to_remove.append(condition_id)
        
        for condition_id in listeners_to_remove:
            await self.remove_listener(condition_id)
        
        return removed_count
    
    @property
    def all_alerts(self) -> Dict[str, CompositeListener]:
        """Возвращает словарь всех активных алертов.

        Returns:
            Dict[str, CompositeListener]: Словарь с ID условий в качестве ключей
                и соответствующими слушателями в качестве значений.
        """
        return self._listeners

    async def _process_listener_with_semaphore(
        self, listener_id: str, listener: CompositeListener
    ) -> None:
        """Проверяет одного слушателя с ограничением семафора.

        Выполняет проверку условий алерта для одного слушателя внутри
        семафора для контроля параллельности.

        Args:
            listener_id: ID условия слушателя для логирования.
            listener: Экземпляр композитного слушателя для проверки.

        Raises:
            Exception: Любые ошибки проверки слушателя логируются, но не пробрасываются.
        """
        async with self.semaphore:
            try:
                logger.debug(f"[TICK] {listener_id}")
                await listener.maybe_update()
            except Exception as exc:
                logger.exception(f"[ERROR] {listener_id}: {exc!r}")

    async def tick(self) -> None:
        """Обрабатывает алерты пакетами с динамическим размером.

        Выполняет проверку всех активных слушателей, разбивая их на пакеты
        для эффективной обработки больших количеств алертов. Размер пакета
        и задержки между пакетами адаптируются в зависимости от общего количества алертов.

        Логика размеров пакетов:
        - ≤1000 алертов: пакеты по 500, пауза 0.1с
        - ≤5000 алертов: пакеты по 1000, пауза 0.05с  
        - ≤15000 алертов: пакеты по 1500, пауза 0.05с
        - >15000 алертов: пакеты по 2000, пауза 0.02с

        Raises:
            Exception: Ошибки обработки отдельных слушателей логируются
                в _process_listener_with_semaphore, но не прерывают общую обработку.
        """
        listeners_items = list(self._listeners.items())
        total_listeners = len(listeners_items)
        
        if not total_listeners:
            return
        
        # Динамический размер пакета на основе количества алертов
        if total_listeners <= 1000:
            batch_size = 500
        elif total_listeners <= 5000:
            batch_size = 1000
        elif total_listeners <= 15000:
            batch_size = 1500
        else:
            batch_size = 2000
        
        logger.debug(f"[BATCH] Обрабатываем {total_listeners} алертов пакетами по {batch_size}")
        
        for i in range(0, total_listeners, batch_size):
            batch = listeners_items[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_listeners + batch_size - 1) // batch_size
            
            logger.debug(f"[BATCH {batch_num}/{total_batches}] Обрабатываем {len(batch)} алертов")
            
            # Обрабатываем пакет параллельно
            async with asyncio.TaskGroup() as tg:
                for listener_id, listener in batch:
                    tg.create_task(
                        self._process_listener_with_semaphore(listener_id, listener)
                    )
            
            # Адаптивная пауза между пакетами
            if total_listeners > 5000:
                await asyncio.sleep(0.02)
            elif total_listeners > 1000:
                await asyncio.sleep(0.05)
            else:
                await asyncio.sleep(0.1)

    def get_listener_by_id(self, condition_id: str) -> CompositeListener | None:
        """Возвращает слушатель по ID условия.

        Args:
            condition_id: ID условия для поиска слушателя.

        Returns:
            CompositeListener | None: Слушатель если найден, иначе None.
        """
        return self._listeners.get(condition_id)

    def get_user_subscriptions(self, user_id: int) -> Dict[str, CompositeListener]:
        """Возвращает список слушателей, на которые подписан пользователь.

        Проходит по всем слушателям и возвращает те, в подписчиках
        которых находится указанный пользователь.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Dict[str, CompositeListener]: Словарь с ID условий в качестве ключей
                и соответствующими слушателями в качестве значений для всех
                алертов пользователя.
        """
        subscriptions = {}
        for condition_id, listener in self._listeners.items():
            if user_id in listener.subscribers:
                subscriptions[condition_id] = listener
        return subscriptions
