#!/usr/bin/env python3
"""
Demo script to test Lemonade Arcade without needing Lemonade Server
"""

import json
import os
import sys
import time
from pathlib import Path

# Add the package to the path for local testing
sys.path.insert(0, str(Path(__file__).parent))

from lemonade_arcade.main import (
    GAMES_DIR,
    GAME_METADATA,
    save_metadata,
    generate_game_id,
    launch_game,
)

# Sample game code for testing
SAMPLE_SNAKE_GAME = """import pygame
import random
import sys

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 20
GRID_WIDTH = WINDOW_WIDTH // GRID_SIZE
GRID_HEIGHT = WINDOW_HEIGHT // GRID_SIZE

# Colors
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)

class Snake:
    def __init__(self):
        self.positions = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = (1, 0)
        self.grow = False
    
    def move(self):
        head = self.positions[0]
        new_head = (head[0] + self.direction[0], head[1] + self.direction[1])
        
        # Check boundaries
        if (new_head[0] < 0 or new_head[0] >= GRID_WIDTH or 
            new_head[1] < 0 or new_head[1] >= GRID_HEIGHT):
            return False
        
        # Check self collision
        if new_head in self.positions:
            return False
        
        self.positions.insert(0, new_head)
        
        if not self.grow:
            self.positions.pop()
        else:
            self.grow = False
        
        return True
    
    def change_direction(self, direction):
        # Prevent moving backwards
        if (direction[0] * -1, direction[1] * -1) != self.direction:
            self.direction = direction
    
    def eat_food(self):
        self.grow = True

class Food:
    def __init__(self):
        self.position = self.random_position()
        self.move_timer = 0
        self.move_interval = 180  # Move every 3 seconds at 60 FPS
    
    def random_position(self):
        return (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
    
    def update(self, snake_positions):
        self.move_timer += 1
        if self.move_timer >= self.move_interval:
            # Move the food to a new position
            while True:
                new_pos = self.random_position()
                if new_pos not in snake_positions:
                    self.position = new_pos
                    break
            self.move_timer = 0

def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Moving Food Snake - Lemonade Arcade")
    clock = pygame.time.Clock()
    
    snake = Snake()
    food = Food()
    score = 0
    font = pygame.font.Font(None, 36)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    snake.change_direction((0, -1))
                elif event.key == pygame.K_DOWN:
                    snake.change_direction((0, 1))
                elif event.key == pygame.K_LEFT:
                    snake.change_direction((-1, 0))
                elif event.key == pygame.K_RIGHT:
                    snake.change_direction((1, 0))
        
        # Update food position
        food.update(snake.positions)
        
        # Move snake
        if not snake.move():
            # Game over
            game_over_text = font.render(f"Game Over! Score: {score}", True, WHITE)
            screen.blit(game_over_text, (WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2))
            pygame.display.flip()
            pygame.time.wait(3000)
            running = False
            continue
        
        # Check if snake ate food
        if snake.positions[0] == food.position:
            snake.eat_food()
            score += 10
            food.position = food.random_position()
            # Ensure food doesn't appear on snake
            while food.position in snake.positions:
                food.position = food.random_position()
        
        # Draw everything
        screen.fill(BLACK)
        
        # Draw snake
        for position in snake.positions:
            rect = pygame.Rect(position[0] * GRID_SIZE, position[1] * GRID_SIZE, 
                             GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(screen, GREEN, rect)
            pygame.draw.rect(screen, WHITE, rect, 1)
        
        # Draw food (pulsing effect)
        pulse = int(abs(pygame.time.get_ticks() / 200 % 2))
        food_color = RED if pulse else (200, 0, 0)
        food_rect = pygame.Rect(food.position[0] * GRID_SIZE, food.position[1] * GRID_SIZE,
                               GRID_SIZE, GRID_SIZE)
        pygame.draw.rect(screen, food_color, food_rect)
        
        # Draw score
        score_text = font.render(f"Score: {score}", True, WHITE)
        screen.blit(score_text, (10, 10))
        
        # Draw instructions
        inst_text = font.render("Food moves every 3 seconds!", True, BLUE)
        screen.blit(inst_text, (10, WINDOW_HEIGHT - 40))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()

if __name__ == "__main__":
    main()
"""

SAMPLE_PONG_GAME = """import pygame
import random
import sys

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
PADDLE_WIDTH = 15
PADDLE_HEIGHT = 90
BALL_SIZE = 15
PADDLE_SPEED = 6
BALL_SPEED_X = 5
BALL_SPEED_Y = 5

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)

class Paddle:
    def __init__(self, x, y, color):
        self.rect = pygame.Rect(x, y, PADDLE_WIDTH, PADDLE_HEIGHT)
        self.speed = PADDLE_SPEED
        self.color = color
    
    def move_up(self):
        if self.rect.top > 0:
            self.rect.y -= self.speed
    
    def move_down(self):
        if self.rect.bottom < WINDOW_HEIGHT:
            self.rect.y += self.speed
    
    def ai_move(self, ball_y):
        # Simple AI that follows the ball
        center = self.rect.centery
        if center < ball_y - 30:
            self.move_down()
        elif center > ball_y + 30:
            self.move_up()

class Ball:
    def __init__(self):
        self.rect = pygame.Rect(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2, BALL_SIZE, BALL_SIZE)
        self.speed_x = BALL_SPEED_X * random.choice([-1, 1])
        self.speed_y = BALL_SPEED_Y * random.choice([-1, 1])
        self.trail = []
    
    def move(self):
        # Add current position to trail
        self.trail.append((self.rect.centerx, self.rect.centery))
        if len(self.trail) > 10:
            self.trail.pop(0)
        
        self.rect.x += self.speed_x
        self.rect.y += self.speed_y
        
        # Bounce off top and bottom
        if self.rect.top <= 0 or self.rect.bottom >= WINDOW_HEIGHT:
            self.speed_y = -self.speed_y
    
    def reset(self):
        self.rect.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.speed_x = BALL_SPEED_X * random.choice([-1, 1])
        self.speed_y = BALL_SPEED_Y * random.choice([-1, 1])
        self.trail = []

def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Rainbow Pong - Lemonade Arcade")
    clock = pygame.time.Clock()
    
    # Create paddles
    player_paddle = Paddle(30, WINDOW_HEIGHT // 2 - PADDLE_HEIGHT // 2, CYAN)
    ai_paddle = Paddle(WINDOW_WIDTH - 30 - PADDLE_WIDTH, WINDOW_HEIGHT // 2 - PADDLE_HEIGHT // 2, MAGENTA)
    
    ball = Ball()
    
    player_score = 0
    ai_score = 0
    font = pygame.font.Font(None, 74)
    small_font = pygame.font.Font(None, 36)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Player controls
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            player_paddle.move_up()
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_paddle.move_down()
        
        # AI movement
        ai_paddle.ai_move(ball.rect.centery)
        
        # Move ball
        ball.move()
        
        # Ball collision with paddles
        if ball.rect.colliderect(player_paddle.rect):
            ball.speed_x = abs(ball.speed_x)  # Ensure ball goes right
            # Add some randomness to the bounce
            ball.speed_y += random.randint(-2, 2)
        
        if ball.rect.colliderect(ai_paddle.rect):
            ball.speed_x = -abs(ball.speed_x)  # Ensure ball goes left
            ball.speed_y += random.randint(-2, 2)
        
        # Scoring
        if ball.rect.left <= 0:
            ai_score += 1
            ball.reset()
        elif ball.rect.right >= WINDOW_WIDTH:
            player_score += 1
            ball.reset()
        
        # Draw everything
        screen.fill(BLACK)
        
        # Draw dashed center line
        for i in range(0, WINDOW_HEIGHT, 20):
            pygame.draw.rect(screen, WHITE, (WINDOW_WIDTH // 2 - 2, i, 4, 10))
        
        # Draw ball trail
        for i, pos in enumerate(ball.trail):
            alpha = i / len(ball.trail)
            color = (int(255 * alpha), int(255 * alpha), int(255 * alpha))
            pygame.draw.circle(screen, color, pos, int(BALL_SIZE // 2 * alpha))
        
        # Draw paddles
        pygame.draw.rect(screen, player_paddle.color, player_paddle.rect)
        pygame.draw.rect(screen, ai_paddle.color, ai_paddle.rect)
        
        # Draw ball
        pygame.draw.rect(screen, WHITE, ball.rect)
        
        # Draw scores
        player_text = font.render(str(player_score), True, WHITE)
        ai_text = font.render(str(ai_score), True, WHITE)
        screen.blit(player_text, (WINDOW_WIDTH // 4, 50))
        screen.blit(ai_text, (3 * WINDOW_WIDTH // 4, 50))
        
        # Draw controls
        controls = small_font.render("Use UP/DOWN arrows or W/S to move", True, WHITE)
        screen.blit(controls, (WINDOW_WIDTH // 2 - 200, WINDOW_HEIGHT - 30))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()

if __name__ == "__main__":
    main()
"""


def create_demo_games():
    """Create some demo games for testing."""
    print("Creating demo games...")

    # Ensure games directory exists
    GAMES_DIR.mkdir(parents=True, exist_ok=True)

    # Create snake game
    snake_id = generate_game_id()
    snake_file = GAMES_DIR / f"{snake_id}.py"
    with open(snake_file, "w", encoding="utf-8") as f:
        f.write(SAMPLE_SNAKE_GAME)

    GAME_METADATA[snake_id] = {
        "title": "Moving Food Snake",
        "description": "Classic snake game but the food moves around every 3 seconds!",
        "created": time.time(),
    }

    # Create pong game
    pong_id = generate_game_id()
    pong_file = GAMES_DIR / f"{pong_id}.py"
    with open(pong_file, "w", encoding="utf-8") as f:
        f.write(SAMPLE_PONG_GAME)

    GAME_METADATA[pong_id] = {
        "title": "Rainbow Pong",
        "description": "Colorful pong game with trail effects and AI opponent",
        "created": time.time(),
    }

    # Save metadata
    save_metadata()

    print(f"Created demo games:")
    print(f"  - {GAME_METADATA[snake_id]['title']} (ID: {snake_id})")
    print(f"  - {GAME_METADATA[pong_id]['title']} (ID: {pong_id})")

    return snake_id, pong_id


if __name__ == "__main__":
    print("Lemonade Arcade Demo Setup")
    print("=" * 40)

    snake_id, pong_id = create_demo_games()

    print("\nDemo games created successfully!")
    print("You can now run 'lemonade-arcade' to see them in the library.")
    print("\nTo test a specific game directly:")
    print(f"  python {GAMES_DIR / f'{snake_id}.py'}")
    print(f"  python {GAMES_DIR / f'{pong_id}.py'}")
