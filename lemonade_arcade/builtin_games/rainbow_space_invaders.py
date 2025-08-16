#!/usr/bin/env python3
"""
Rainbow Space Invaders - Space invaders with rainbow colors
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
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def get_rainbow_color(time, offset=0):
    """Generate rainbow colors based on time"""
    r = int(127 * (1 + math.sin(time * 0.05 + offset)))
    g = int(127 * (1 + math.sin(time * 0.05 + offset + 2)))
    b = int(127 * (1 + math.sin(time * 0.05 + offset + 4)))
    return (r, g, b)


class Player:
    def __init__(self):
        self.x = WINDOW_WIDTH // 2
        self.y = WINDOW_HEIGHT - 60
        self.width = 40
        self.height = 30
        self.speed = 5
        self.bullets = []
        self.shoot_cooldown = 0

    def update(self):
        keys = pygame.key.get_pressed()

        if keys[pygame.K_LEFT] and self.x > 0:
            self.x -= self.speed
        if keys[pygame.K_RIGHT] and self.x < WINDOW_WIDTH - self.width:
            self.x += self.speed

        if keys[pygame.K_SPACE] and self.shoot_cooldown <= 0:
            self.bullets.append(Bullet(self.x + self.width // 2, self.y))
            self.shoot_cooldown = 10

        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1

        # Update bullets
        for bullet in self.bullets[:]:
            bullet.update()
            if bullet.y < 0:
                self.bullets.remove(bullet)

    def draw(self, screen, time):
        # Draw player ship with rainbow trail effect
        for i in range(5):
            color = get_rainbow_color(time, i * 0.5)
            offset = i * 2

            # Ship body
            ship_rect = pygame.Rect(
                self.x + offset,
                self.y + offset,
                self.width - offset * 2,
                self.height - offset * 2,
            )
            pygame.draw.rect(screen, color, ship_rect)

        # Draw bullets
        for bullet in self.bullets:
            bullet.draw(screen, time)


class Bullet:
    def __init__(self, x, y, speed=-8):
        self.x = x
        self.y = y
        self.width = 4
        self.height = 10
        self.speed = speed

    def update(self):
        self.y += self.speed

    def draw(self, screen, time):
        color = get_rainbow_color(time * 2, self.x * 0.1)
        bullet_rect = pygame.Rect(
            self.x - self.width // 2, self.y, self.width, self.height
        )
        pygame.draw.rect(screen, color, bullet_rect)

    def get_rect(self):
        return pygame.Rect(self.x - self.width // 2, self.y, self.width, self.height)


class Invader:
    def __init__(self, x, y, color_offset):
        self.x = x
        self.y = y
        self.width = 30
        self.height = 20
        self.color_offset = color_offset
        self.alive = True
        self.bullets = []
        self.shoot_timer = random.randint(60, 180)

    def update(self, direction_x, move_down):
        if move_down:
            self.y += 20
        else:
            self.x += direction_x

        # Shooting
        self.shoot_timer -= 1
        if self.shoot_timer <= 0 and random.random() < 0.01:
            self.bullets.append(
                Bullet(self.x + self.width // 2, self.y + self.height, 4)
            )
            self.shoot_timer = random.randint(120, 300)

        # Update bullets
        for bullet in self.bullets[:]:
            bullet.update()
            if bullet.y > WINDOW_HEIGHT:
                self.bullets.remove(bullet)

    def draw(self, screen, time):
        if self.alive:
            color = get_rainbow_color(time, self.color_offset)

            # Draw invader with animated effect
            pulse = abs(math.sin(time * 0.1 + self.color_offset))
            size_mod = int(pulse * 5)

            invader_rect = pygame.Rect(
                self.x - size_mod,
                self.y - size_mod,
                self.width + size_mod * 2,
                self.height + size_mod * 2,
            )
            pygame.draw.rect(screen, color, invader_rect)

            # Draw eyes
            eye_color = WHITE
            eye1 = pygame.Rect(self.x + 5, self.y + 5, 6, 6)
            eye2 = pygame.Rect(self.x + self.width - 11, self.y + 5, 6, 6)
            pygame.draw.rect(screen, eye_color, eye1)
            pygame.draw.rect(screen, eye_color, eye2)

        # Draw bullets
        for bullet in self.bullets:
            bullet.draw(screen, time)

    def get_rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)


class InvaderGroup:
    def __init__(self):
        self.invaders = []
        self.direction = 1
        self.move_down = False

        # Create grid of invaders
        for row in range(5):
            for col in range(10):
                x = 100 + col * 60
                y = 50 + row * 50
                color_offset = row * 2 + col * 0.5
                self.invaders.append(Invader(x, y, color_offset))

    def update(self):
        # Check if any invader hit the edge
        hit_edge = False
        for invader in self.invaders:
            if invader.alive:
                if (invader.x <= 0 and self.direction < 0) or (
                    invader.x >= WINDOW_WIDTH - invader.width and self.direction > 0
                ):
                    hit_edge = True
                    break

        if hit_edge:
            self.direction *= -1
            self.move_down = True
        else:
            self.move_down = False

        # Update all invaders
        for invader in self.invaders:
            if invader.alive:
                invader.update(self.direction * 2, self.move_down)

    def draw(self, screen, time):
        for invader in self.invaders:
            invader.draw(screen, time)

    def check_collisions(self, player_bullets):
        hits = 0
        for bullet in player_bullets[:]:
            bullet_rect = bullet.get_rect()
            for invader in self.invaders:
                if invader.alive and bullet_rect.colliderect(invader.get_rect()):
                    invader.alive = False
                    player_bullets.remove(bullet)
                    hits += 1
                    break
        return hits

    def get_bullets(self):
        bullets = []
        for invader in self.invaders:
            bullets.extend(invader.bullets)
        return bullets

    def alive_count(self):
        return sum(1 for invader in self.invaders if invader.alive)

    def lowest_y(self):
        lowest = 0
        for invader in self.invaders:
            if invader.alive and invader.y > lowest:
                lowest = invader.y
        return lowest


def create_star_field():
    """Create animated star background"""
    stars = []
    for _ in range(100):
        x = random.randint(0, WINDOW_WIDTH)
        y = random.randint(0, WINDOW_HEIGHT)
        speed = random.uniform(0.5, 2.0)
        brightness = random.randint(50, 255)
        stars.append([x, y, speed, brightness])
    return stars


def update_star_field(stars):
    """Update star positions"""
    for star in stars:
        star[1] += star[2]  # Move down
        if star[1] > WINDOW_HEIGHT:
            star[1] = 0
            star[0] = random.randint(0, WINDOW_WIDTH)


def draw_star_field(screen, stars, time):
    """Draw animated stars"""
    for star in stars:
        pulse = abs(math.sin(time * 0.02 + star[0] * 0.01))
        brightness = int(star[3] * pulse)
        color = (brightness, brightness, brightness)
        pygame.draw.circle(screen, color, (int(star[0]), int(star[1])), 1)


def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Rainbow Space Invaders")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 36)

    player = Player()
    invaders = InvaderGroup()
    stars = create_star_field()
    score = 0
    game_over = False
    victory = False
    time = 0

    while True:
        time += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if (game_over or victory) and event.key == pygame.K_SPACE:
                    # Restart game
                    player = Player()
                    invaders = InvaderGroup()
                    score = 0
                    game_over = False
                    victory = False
                    time = 0

        if not game_over and not victory:
            # Update game objects
            player.update()
            invaders.update()
            update_star_field(stars)

            # Check collisions
            hits = invaders.check_collisions(player.bullets)
            score += hits * 10

            # Check if player hit by invader bullets
            player_rect = pygame.Rect(player.x, player.y, player.width, player.height)
            for bullet in invaders.get_bullets():
                if bullet.get_rect().colliderect(player_rect):
                    game_over = True

            # Check win condition
            if invaders.alive_count() == 0:
                victory = True

            # Check lose condition (invaders reach bottom)
            if invaders.lowest_y() > WINDOW_HEIGHT - 100:
                game_over = True

        # Draw everything
        screen.fill(BLACK)

        # Draw star field
        draw_star_field(screen, stars, time)

        if not game_over and not victory:
            player.draw(screen, time)
            invaders.draw(screen, time)

        # Draw score with rainbow effect
        score_color = get_rainbow_color(time * 0.5)
        score_text = font.render(f"Score: {score}", True, score_color)
        screen.blit(score_text, (10, 10))

        # Draw game state messages
        if game_over:
            game_over_color = get_rainbow_color(time)
            game_over_text = font.render("GAME OVER", True, game_over_color)
            restart_text = font.render("Press SPACE to restart", True, WHITE)

            game_over_rect = game_over_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 20)
            )
            restart_rect = restart_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20)
            )

            screen.blit(game_over_text, game_over_rect)
            screen.blit(restart_text, restart_rect)

        elif victory:
            victory_color = get_rainbow_color(time * 2)
            victory_text = font.render("VICTORY!", True, victory_color)
            restart_text = font.render("Press SPACE to play again", True, WHITE)

            victory_rect = victory_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 20)
            )
            restart_rect = restart_text.get_rect(
                center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20)
            )

            screen.blit(victory_text, victory_rect)
            screen.blit(restart_text, restart_rect)

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
