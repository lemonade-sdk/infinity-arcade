#!/usr/bin/env python3
"""
Dynamic Snake Game - Snake but the food moves around
Built-in game for Lemonade Arcade
"""

import pygame
import random
import sys
import math

# Initialize Pygame
pygame.init()

# Game constants
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
YELLOW = (255, 255, 0)
BLUE = (0, 100, 255)


class Snake:
    def __init__(self):
        self.body = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = (1, 0)
        self.grow_next = False

    def move(self):
        head_x, head_y = self.body[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        # Check wall collision
        if (
            new_head[0] < 0
            or new_head[0] >= GRID_WIDTH
            or new_head[1] < 0
            or new_head[1] >= GRID_HEIGHT
        ):
            return False

        # Check self collision
        if new_head in self.body:
            return False

        self.body.insert(0, new_head)

        if not self.grow_next:
            self.body.pop()
        else:
            self.grow_next = False

        return True

    def grow(self):
        self.grow_next = True

    def draw(self, screen):
        for i, segment in enumerate(self.body):
            x, y = segment
            rect = pygame.Rect(x * GRID_SIZE, y * GRID_SIZE, GRID_SIZE, GRID_SIZE)

            if i == 0:  # Head
                pygame.draw.rect(screen, GREEN, rect)
                pygame.draw.rect(screen, WHITE, rect, 2)
            else:  # Body
                pygame.draw.rect(screen, GREEN, rect)
                pygame.draw.rect(screen, BLACK, rect, 1)


class MovingFood:
    def __init__(self):
        self.position = self.random_position()
        self.direction = self.random_direction()
        self.speed = 0.1  # Speed of movement
        self.float_pos = [float(self.position[0]), float(self.position[1])]
        self.change_direction_timer = 0
        self.pulse_time = 0

    def random_position(self):
        return (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))

    def random_direction(self):
        angle = random.uniform(0, 2 * math.pi)
        return (math.cos(angle), math.sin(angle))

    def update(self, snake_body):
        self.pulse_time += 0.2
        self.change_direction_timer += 1

        # Change direction randomly every 2-4 seconds
        if self.change_direction_timer > random.randint(120, 240):
            self.direction = self.random_direction()
            self.change_direction_timer = 0

        # Move the food
        self.float_pos[0] += self.direction[0] * self.speed
        self.float_pos[1] += self.direction[1] * self.speed

        # Bounce off walls
        if self.float_pos[0] <= 0 or self.float_pos[0] >= GRID_WIDTH - 1:
            self.direction = (-self.direction[0], self.direction[1])
            self.float_pos[0] = max(1, min(GRID_WIDTH - 2, self.float_pos[0]))

        if self.float_pos[1] <= 0 or self.float_pos[1] >= GRID_HEIGHT - 1:
            self.direction = (self.direction[0], -self.direction[1])
            self.float_pos[1] = max(1, min(GRID_HEIGHT - 2, self.float_pos[1]))

        # Update grid position
        self.position = (int(self.float_pos[0]), int(self.float_pos[1]))

        # Avoid spawning on snake
        if self.position in snake_body:
            self.direction = self.random_direction()

    def draw(self, screen):
        x, y = self.position
        rect = pygame.Rect(x * GRID_SIZE, y * GRID_SIZE, GRID_SIZE, GRID_SIZE)

        # Pulsing effect
        pulse = abs(math.sin(self.pulse_time))
        color_intensity = int(200 + 55 * pulse)
        color = (color_intensity, 0, 0)

        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, YELLOW, rect, 2)


def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Dynamic Snake - Moving Food Edition")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 36)

    snake = Snake()
    food = MovingFood()
    score = 0
    game_over = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if game_over:
                    if event.key == pygame.K_SPACE:
                        # Restart game
                        snake = Snake()
                        food = MovingFood()
                        score = 0
                        game_over = False
                else:
                    # Snake controls
                    if event.key == pygame.K_UP and snake.direction != (0, 1):
                        snake.direction = (0, -1)
                    elif event.key == pygame.K_DOWN and snake.direction != (0, -1):
                        snake.direction = (0, 1)
                    elif event.key == pygame.K_LEFT and snake.direction != (1, 0):
                        snake.direction = (-1, 0)
                    elif event.key == pygame.K_RIGHT and snake.direction != (-1, 0):
                        snake.direction = (1, 0)

        if not game_over:
            # Update food position
            food.update(snake.body)

            # Move snake
            if not snake.move():
                game_over = True

            # Check food collision
            if snake.body[0] == food.position:
                snake.grow()
                score += 10
                food = MovingFood()  # Create new moving food

        # Draw everything
        screen.fill(BLACK)

        if not game_over:
            snake.draw(screen)
            food.draw(screen)

        # Draw score
        score_text = font.render(f"Score: {score}", True, WHITE)
        screen.blit(score_text, (10, 10))

        if game_over:
            game_over_text = font.render("GAME OVER", True, RED)
            restart_text = font.render("Press SPACE to restart", True, WHITE)

            game_over_rect = game_over_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 20)
            )
            restart_rect = restart_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20)
            )

            screen.blit(game_over_text, game_over_rect)
            screen.blit(restart_text, restart_rect)

        pygame.display.flip()
        clock.tick(10)  # Snake speed


if __name__ == "__main__":
    main()

# Copyright (c) 2025 AMD
