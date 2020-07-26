# git-delete-merged-branches

A convenient command-line tool helping you keep repositories clean.


# Installation

```console
pip install git-delete-merged-branches
```


# Features

- Supports deletion of both local and remote branches
- Supports workflows with multiple release branches, e.g. only delete branches that have been merged to *all* of `master`, `dev`  and `staging`
- Quick interactive configuration
- Provider agnostic: Works with GitHub, GitLab and any other Git hosting
- Takes safety seriously


# Safety

Deletion is a sharp knife that requires care.
While `git reflog` would have your back in most cases,
`git-delete-merged-branches` takes safety seriously.

Here's what `git-delete-merged-branches` does for your safety:
- No branches are deleted without confirmation or passing `--yes`.
- Confirmation defaults to "no"; plain `[Enter]`/`[Return]` does not delete.
- `git push` is used with `--force-with-lease` so if the server and you have a different understanding of that branch, it is not deleted.
- There is no use of `os.system` or shell code to go wrong.
- With `--dry-run` you can get a feel for the changes that `git-delete-merged-branches` would be making to your branches.
- Show any Git commands run using `--verbose`.


# Best Practices

- Consider running `git remote update --prune` before using `git-delete-merged-branches` for best results.
- Consider using `ssh-agent` if you don't want to enter your SSH key password for each `git push` when working with multiple remotes.


# Support

Please report any bugs that you find.

Like this tool?  Support it with a star!
