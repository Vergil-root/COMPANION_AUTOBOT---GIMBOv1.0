from enum import Enum, auto
from dataclasses import dataclass
from typing import Any

class LifeState(Enum):
    AWAKE = auto()
    SLEEPING = auto()
    SHUTDOWN = auto()

class ActivityState(Enum):
    IDLE = auto()
    LISTENING = auto()
    MOVING = auto()
    INTERACTING = auto()
    EXPLORING = auto()
    RESTING = auto()
    EVADING = auto() 

class Mood(Enum):
    HAPPY = auto()
    CURIOUS = auto()
    SLEEPY = auto()
    SAD = auto()
    ANGRY = auto()

class EventType(Enum):
    VOICE_COMMAND = auto()
    FACE_DETECTED = auto()
    FACE_LOST = auto()
    OBSTACLE = auto()
    BATTERY_UPDATE = auto() 
    WAKE = auto()
    SLEEP = auto()
    SHUTDOWN = auto()
    PHYSICAL_EXPRESSION = auto()
    DRIVE_COMMAND = auto()

@dataclass
class Event:
    type: EventType
    data: Any = None
