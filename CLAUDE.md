# Rules (always apply)
- NEVER run git push, change remotes, or touch git config. The owner pushes.
- Commit locally often, with clear messages. NEVER add Co-Authored-By, "Generated with Claude Code", or any Claude attribution to commits or files.
- Keep results/EXPERIMENTS.md: for every experiment log hypothesis, the ONE change, command, validation metrics, keep/revert decision, commit hash. Write keep/revert rules BEFORE seeing results.
- Split by TIME only, never random. Every load-based feature must be known at least 24h before the target hour.
- The final test period is touched ONCE, in Phase 6, by scripts/final_eval.py --confirm-final. Never load it before that.
- Tune on validation only. Fixed seeds. Max 10 experiments per feature group.
- Stay inside this folder. No deletes outside it. Do not commit raw data files (use .gitignore) or secrets.
- Verify every README claim against the code.
- At each CHECKPOINT: print a short plain summary and STOP until the owner says "continue".
