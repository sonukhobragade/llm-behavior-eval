"""Allow running as `python -m llmeval`."""
import sys

from llmeval.cli import main

# Propagate the exit code. Discarding it meant every run exited 0, so a
# scheduled evaluation reported success no matter what it found.
sys.exit(main())
