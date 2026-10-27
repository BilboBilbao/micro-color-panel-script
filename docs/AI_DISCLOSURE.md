# AI disclosure

**All code in this project was written by an AI: Claude, made by Anthropic.** This covers the program (`panel_main.py` and the `micropanel` package),
the diagnose mode, the tests, the tools and the documentation.

## Who did what

- **Claude** wrote the code, the tests and the documents, and explained each change.
- **The project owner** is not a programmer. They set the goals, decided every design question
  (for example the license and the rules for button combinations), approved each change before it was made,
  applied the changes in their own folder and **tested everything on real hardware**
  (a Micro Color Panel with DaVinci Resolve on Windows 11).

## Limits of this process

- Claude could not run the program, Git, Python or Resolve itself. Every run, every test result and every statement
  about the hardware comes from the owner's machine.
- Claude's code is checked by automatic tests (`python -m pytest -q`) and by an assisted diagnose mode (`--diagnose`).
  These tests prove the logic. Only the hardware runs prove that the panel, the mouse and Resolve behave as described.
- The project was reviewed twice by other AI systems (three reviewers each time), without a human programmer.
  The next review is planned after the next development phase. Reports from users are welcome.

## What this means for you

Treat the program like software from any other hobby project: read the compatibility table in the README,
and note that only the combinations listed as tested there were tried.