# Homework rubrics

One file per task. Each says what the task asks for and how it is checked:

- **Automatic checks**: what `.github/scripts/check_<task>.py` decides. These results are final.
- **AI checks**: the rules a script can't judge. The AI reviewer (`ai_review.py`) reads this file
  and judges only these rules. A task without this section gets no AI review.
- **Decided by a teacher**: cases the script recognizes but can't settle from the code. They
  never fail the task: the review says a teacher will check, with the `needs-teacher` label.
- **Not checked**: what nobody can verify from the repository.

The batch grading reads the same files, so CI and the emails apply one set of rules.
Change a rule here and in the checker together.
