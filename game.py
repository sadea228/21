import random
from typing import List, Dict, Tuple, Optional, Union

# Константы для карт
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 10, 'Q': 10, 'K': 10, 'A': 11
}

# Красивые эмодзи для мастей
SUIT_EMOJI = {
    '♠': '♠️', # Пики (черные)
    '♥': '♥️', # Червы (красные)
    '♦': '♦️', # Бубны (красные)
    '♣': '♣️'  # Трефы (черные)
}

# Красивые отображения для картинок
FACE_CARDS = {
    'J': 'J', # Валет
    'Q': 'Q', # Дама
    'K': 'K', # Король
    'A': 'A'  # Туз
}

class Card:
    def __init__(self, rank: str, suit: str):
        self.rank = rank
        self.suit = suit
        self.value = RANK_VALUES[rank]

    def __str__(self):
        # Используем эмодзи для мастей
        emoji_suit = SUIT_EMOJI.get(self.suit, self.suit)
        
        # Добавляем отступ после ранга для лучшего отображения
        rank_display = self.rank
        if len(rank_display) == 1:  # Если ранг одиночный символ (не 10)
            rank_display += " "
            
        return f"{rank_display}{emoji_suit}"

class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self.cards)

    def deal_card(self) -> Optional[Card]:
        if not self.cards:
            return None
        return self.cards.pop()

class Player:
    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        self.cards = []
        self.stopped = False
        self.busted = False

    def add_card(self, card: Card) -> None:
        self.cards.append(card)
        self.busted = self.get_score() > 21

    def get_score(self) -> int:
        score = sum(card.value for card in self.cards)
        # Обработка тузов для предотвращения перебора
        aces = sum(1 for card in self.cards if card.rank == 'A')
        while score > 21 and aces > 0:
            score -= 10  # Уменьшаем ценность туза с 11 до 1
            aces -= 1
        return score

    def get_cards_str(self) -> str:
        """Возвращает строковое представление карт игрока"""
        if not self.cards:
            return "нет карт"
        return " ".join(f"[{str(card)}]" for card in self.cards)

class Game:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.deck = Deck()
        self.players: Dict[int, Player] = {}
        self.current_player_id: Optional[int] = None
        self.started = False
        self.finished = False
        self.winner_id: Optional[int] = None
        self.is_draw = False

    def add_player(self, user_id: int, username: str) -> bool:
        """Добавляет игрока в игру. Возвращает True если игра может начаться."""
        if len(self.players) >= 2 or self.started:
            return False

        self.players[user_id] = Player(user_id, username)
        
        # Если это второй игрок, игра может начаться
        return len(self.players) == 2

    def start_game(self) -> None:
        """Начинает игру, раздает начальные карты."""
        if len(self.players) != 2:
            return
            
        self.started = True
        
        # Раздаем по две карты каждому игроку
        for player in self.players.values():
            player.add_card(self.deck.deal_card())
            player.add_card(self.deck.deal_card())
        
        # Устанавливаем первого игрока
        self.current_player_id = next(iter(self.players.keys()))

    def next_turn(self) -> None:
        """Переход хода к следующему игроку."""
        if not self.started or self.finished:
            return
            
        # Находим всех игроков, которые еще не остановились и не перебрали
        active_players = [pid for pid, player in self.players.items() 
                          if not player.stopped and not player.busted]
        
        if not active_players:
            # Нет активных игроков, завершаем игру
            self.finish_game()
            return
        
        if len(active_players) == 1:
            # Один активный игрок
            self.current_player_id = active_players[0]
        else:
            # Переключаем между двумя игроками
            player_ids = list(self.players.keys())
            current_index = player_ids.index(self.current_player_id)
            next_index = (current_index + 1) % 2
            self.current_player_id = player_ids[next_index]
            
            # Если следующий игрок уже остановился или перебрал, вернемся к первому
            if self.players[self.current_player_id].stopped or self.players[self.current_player_id].busted:
                self.current_player_id = player_ids[current_index]

    def hit(self, user_id: int) -> Tuple[bool, Optional[Card]]:
        """Игрок берет карту. Возвращает (успех, карта)."""
        if not self.started or self.finished or self.current_player_id != user_id:
            return False, None
            
        player = self.players.get(user_id)
        if not player or player.stopped or player.busted:
            return False, None
            
        card = self.deck.deal_card()
        if not card:
            return False, None
            
        player.add_card(card)
        
        # Если игрок перебрал, проверяем завершение игры
        if player.busted:
            self.check_game_end()
        
        return True, card

    def stand(self, user_id: int) -> bool:
        """Игрок останавливается. Возвращает успех операции."""
        if not self.started or self.finished or self.current_player_id != user_id:
            return False
            
        player = self.players.get(user_id)
        if not player or player.stopped or player.busted:
            return False
            
        player.stopped = True
        
        # Проверяем, завершилась ли игра
        self.check_game_end()
        
        return True

    def check_game_end(self) -> bool:
        """Проверяет, закончилась ли игра. Возвращает True, если игра завершена."""
        if self.finished:
            return True
            
        active_players = [pid for pid, player in self.players.items() 
                        if not player.stopped and not player.busted]
                        
        if not active_players:
            self.finish_game()
            return True
            
        # Если один игрок перебрал, а второй еще может ходить, игра продолжается
        return False

    def finish_game(self) -> None:
        """Завершает игру и определяет победителя."""
        if self.finished:
            return
            
        self.finished = True
        
        player_ids = list(self.players.keys())
        if len(player_ids) != 2:
            return
            
        player1, player2 = self.players[player_ids[0]], self.players[player_ids[1]]
        
        # Проверяем на перебор
        if player1.busted and player2.busted:
            # Оба перебрали - оба проиграли
            self.is_draw = True
            return
            
        if player1.busted:
            self.winner_id = player2.user_id
            return
            
        if player2.busted:
            self.winner_id = player1.user_id
            return
            
        # Сравниваем очки
        score1, score2 = player1.get_score(), player2.get_score()
        
        if score1 > score2:
            self.winner_id = player1.user_id
        elif score2 > score1:
            self.winner_id = player2.user_id
        else:
            self.is_draw = True

    def get_status_message(self) -> str:
        """Возвращает текстовое сообщение с текущим статусом игры."""
        if not self.started:
            return "🎮 Игра еще не началась."
            
        if not self.finished:
            current_player = self.players.get(self.current_player_id)
            if current_player:
                return f"🎯 Сейчас ход игрока *{current_player.username}*."
            return "🎲 Игра в процессе."
            
        # Игра завершена
        result = "🏁 *Игра завершена!*\n\n"
        
        for player in self.players.values():
            result += f"👤 *{player.username}*: {player.get_cards_str()} = *{player.get_score()}* очков"
            if player.busted:
                result += " (💥 Перебор!)"
            result += "\n"
            
        if self.is_draw:
            result += "\n🤝 *Ничья!*"
        elif self.winner_id:
            winner = self.players.get(self.winner_id)
            if winner:
                result += f"\n🏆 *Победитель: {winner.username}!*"
                
        return result

# Словарь для хранения активных игр (chat_id -> Game)
active_games = {} 