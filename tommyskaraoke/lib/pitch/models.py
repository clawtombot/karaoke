from dataclasses import dataclass


@dataclass
class PitchNote:
    t: float  # time in seconds
    hz: float  # frequency in Hz
    midi: int  # MIDI note number (69 = A4 = 440Hz)
    voiced: bool  # whether this frame is voiced
    amp: float = 1.0  # normalized amplitude (0-1, relative to peak RMS)
