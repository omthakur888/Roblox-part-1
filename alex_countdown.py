"""Alex Countdown (Part 1) - the whole story, written as code.
Run: python alex_countdown.py
"""
import time

YEAR = 365 * 24 * 3600


class Person:
    def __init__(self, name, role, years=None, seconds=None):
        self.name = name
        self.role = role
        # every person's life is just a countdown in seconds
        self.seconds = seconds if seconds is not None else years * YEAR

    def countdown(self):
        if self.seconds >= YEAR:
            return f"{self.seconds // YEAR} YEARS"
        if self.seconds <= 0:
            return "0 DAYS LEFT"
        return f"00:00:{self.seconds:02d}"

    def __repr__(self):
        return f"{self.name} [{self.countdown()}]"


class World:
    def __init__(self):
        self.people = {}
        self.fate_delayed = False

    def add(self, key, person):
        self.people[key] = person

    def check(self, key):
        return self.people[key].countdown()


def say(text, pause=1.2):
    print(text)
    time.sleep(pause)


def scene(n, title):
    print(f"\n--- SCENE {n}: {title} ---")
    time.sleep(0.6)


def main():
    world = World()
    world.add("alex", Person("Alex", "hero", seconds=0))
    world.add("jake", Person("Jake", "best friend", years=47))
    world.add("mom", Person("Mom", "mother", years=32))
    world.add("mia", Person("Mia", "little sister", years=68))
    world.add("doctor", Person("Doctor", "keeper of secrets", years=20))

    scene(1, "Hook")
    say("Imagine living in a world where everyone knows exactly when they're going to die...")

    scene(2, "Everyone has a countdown")
    say("Everyone has a countdown above their head.")

    scene(3, "The people he loves")
    for key in ("jake", "mom", "mia"):
        p = world.people[key]
        say(f"{p.name} ({p.role}) -> {world.check(key)}")

    scene(4, "Alex checks his own")
    say("But when Alex checks his own countdown...")
    say(f"Alex -> {world.check('alex')}", 2)

    scene(5, "He panics")
    for _ in range(3):
        say("*runs through the dark street*", 0.5)

    scene(6, "The doctor")
    say("Doctor (whispering): \"You're not supposed to be alive.\"", 2)

    scene(7, "The notification")
    world.fate_delayed = True
    say("[GLITCH] YOUR DEATH HAS BEEN DELAYED.")
    say("[GLITCH] SOMEONE ELSE WILL DIE IN YOUR PLACE.", 2)

    scene(8, "Look behind you")
    say("Alex turns around. Mia is standing there.")
    mia = world.people["mia"]
    mia.seconds = 59  # her countdown flips from years to seconds
    while mia.seconds > 55:
        say(f"Mia -> {mia.countdown()}", 0.8)
        mia.seconds -= 1

    scene(9, "Ending")
    say("Alex: NOOOOO!", 1.5)
    print("\n" + "TO BE CONTINUED...".center(40))


if __name__ == "__main__":
    main()
