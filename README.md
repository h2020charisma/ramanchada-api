# ramanchada-api

## Dev notes

### Submodule update

Add and commit or stash any uncommitted changes, then run:
```
git submodule update --remote
git commit -am "Pull the latest commit for the submodules"
git push
```

### Run interminal
```
uvicorn app.main:app --reload
```