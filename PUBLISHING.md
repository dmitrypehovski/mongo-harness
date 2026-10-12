# Publishing to PyPI

The package name `mongo-harness` is **free on PyPI** (checked: the JSON API answers 404), so the
name in `pyproject.toml` can be used as it is.

Everything up to the last step is already done and verified in the repository:

```bash
python -m build          # sdist + wheel
twine check dist/*       # both PASSED
bash scripts/check_dist.sh   # 73 files in the sdist, nothing heavy, every doc and test present
```

## The last step needs one of two things from you

### Option A — trusted publishing (recommended, no token anywhere)

PyPI verifies the GitHub workflow's identity through OIDC, so no long-lived secret exists and
nothing has to be pasted into a chat.

1. Sign in at <https://pypi.org/manage/account/publishing/>.
2. Add a **pending publisher** with exactly these values:
   * PyPI project name: `mongo-harness`
   * Owner: `dmitrypehovski`
   * Repository name: `mongo-harness`
   * Workflow name: `release.yml`
   * Environment name: `pypi`
3. Tag a release and push it:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The `release` workflow builds, checks the distributions, and publishes. Nothing else to configure.

### Option B — an API token

If you would rather use a token than a trusted publisher:

1. <https://pypi.org/manage/account/token/> → create a token scoped to the project `mongo-harness`.
2. Put it in the repository as an encrypted secret named `PYPI_API_TOKEN`
   (Settings → Secrets and variables → Actions → New repository secret). Do not paste it into chat;
   the secret form is the safe place for it.
3. Change the publish step in `.github/workflows/release.yml` to pass it:

```yaml
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

## After the first release

* Bump `version` in `pyproject.toml`, commit, then tag and push. A tag that does not match the
  version in the manifest publishes the manifest's version, which is how a project ends up with two
  artefacts claiming one number — so keep them equal.
* Test installs from the published artefact, not from the checkout:
  `pip install mongo-harness` in a fresh virtualenv, then `mh --help` and `harness-web`.
* The optional extras to mention in the release notes: `mongo-harness[memory]` adds the embedding
  model used for lesson recall; `mongo-harness[dev]` adds pytest.
