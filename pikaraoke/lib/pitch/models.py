from dataclasses import dataclass


@dataclass
class PitchNote:
    t: float  # time in seconds
    hz: float  # frequency in Hz
    midi: int  # MIDI note number (69 = A4 = 440Hz)
    voiced: bool  # whether this frame is voiced
