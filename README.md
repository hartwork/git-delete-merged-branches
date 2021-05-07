# git-delete-merged-branches

A convenient command-line tool helping you keep repositories clean.


# Installation

```console
# pip install git-delete-merged-branches
```


# Example

```console
# git-delete-merged-branches
Do you want to run "git remote update --prune" for 1 remote(s):
  - origin

Update? [y/N] y

Do you want to run "git pull --ff-only" for 1 branch(es):
  - master

Pull? [y/N] y

You are about to delete 6 local branch(es):
  - improve-setup-py
  - issue-12-enable-ci-for-pull-requests
  - issue-5-fix-waste-of-one-second-per-service
  - keep-github-actions-up-to-date
  - refactoring-one
  - simple-ci

Delete? [y/N] y

6 local branch(es) deleted.
You are about to delete 6 remote branch(es):
  - origin/improve-setup-py
  - origin/issue-12-enable-ci-for-pull-requests
  - origin/issue-5-fix-waste-of-one-second-per-service
  - origin/keep-github-actions-up-to-date
  - origin/refactoring-one
  - origin/simple-ci

Delete? [y/N] y
To github.com:hartwork/wait-for-it.git
 - [deleted]         improve-setup-py
 - [deleted]         issue-12-enable-ci-for-pull-requests
 - [deleted]         issue-5-fix-waste-of-one-second-per-service
 - [deleted]         keep-github-actions-up-to-date
 - [deleted]         refactoring-one
 - [deleted]         simple-ci

6 remote branch(es) deleted.
```


# Features

- Supports deletion of both local and remote branches
- Detects multiple forms of de-facto merges
  (rebase merges,
  squash merges (needs `--effort=3`),
  single or range cherry-picks…
  leveraging `git cherry`)
- Supports workflows with multiple release branches, e.g. only delete branches that have been merged to *all* of `master`, `dev`  and `staging`
- Quick interactive configuration
- Provider agnostic: Works with GitHub, GitLab, Gitea and any other Git hosting
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

When the repository is a fork
(with an upstream remote and a fork remote):

- Make sure that release branches are tracking the right remote,
  e.g. `master` should probably track original upstream's `master`
  rather than `master` of your fork.
- Consider keeping your fork's remote `master` up to date (using `git push`).

When using GitHub:

- You can make GitHub
  [delete branches of merged pull requests](https://docs.github.com/en/github/administering-a-repository/managing-the-automatic-deletion-of-branches)
  for you, to save `git-delete-merged-branches` some work on the remote side, if you like.


# Name clash on "git-delete-merged-branches" with git-extras

Utility collection [git-extras](https://github.com/tj/git-extras) provides a
[simple shell script named `git-delete-merged-branches`](https://github.com/tj/git-extras/blob/master/bin/git-delete-merged-branches)
that competes for command `git-delete-merged-branches` when both software packages are installed.

To address this conflict you can:

- a) Invoke `python3 -m git_delete_merged_branches` instead of `git-delete-merged-branches`
- b) Invoke command `git-dmb` instead of `git-delete-merged-branches`
- c) Control path resolution order through environment variable `$PATH`
- d) Invoke `git-delete-merged-branches` with its absolute path.
     You can run `which -a git-delete-merged-branches` to see where it's located.


# Support

Please report any bugs that you find.

Like this tool?  Support it with a star!
