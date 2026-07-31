# FAQ

## Why are my search results not what I expected?

Common causes:

- Network congestion or transient API errors.
- Hitting the rate limit of the arXiv API policy (one request every three
  seconds).
- Query syntax issues: the arXiv API validates queries and rejects malformed
  expressions; check the
  [query syntax documentation](https://info.arxiv.org/help/api/user-manual.html#query_details).

## Can I use the library in a commercial project?

Yes. The library is licensed under the MIT license, which allows use in
commercial projects.

## How can I contribute to the project?

You can contribute by:

- opening issues on the GitHub repository,
- submitting pull requests,
- providing feedback on the project,
- sharing the project with others,
- writing documentation.

See the [Contributing](contributing.md) guide for the development workflow.

## How can I report a bug?

Open an issue on the
[GitHub repository](https://github.com/BalconyJH/aioarxiv/issues/new). Please
provide detailed information about the bug, including steps to reproduce it
and any error messages you received.

## Is there a CLI?

Not yet. A command-line interface may be added in the future.
