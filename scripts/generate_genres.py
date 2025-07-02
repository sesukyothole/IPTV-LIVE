# Add this under your existing "run" steps (after the EPG update is complete)
- name: Generate Genres File
  run: python3 scripts/generate_genres.py

# This will move the new genres.xml to the root (if it's not already there)
- name: Move Genres File
  run: mv genres.xml genres.xml

# This will commit the updated EPG and Genres files together
- name: Commit and Push EPG and Genres
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add epg.xml genres.xml
    git diff-index --quiet HEAD || git commit -m "Daily EPG and Genres Update"
    git push
