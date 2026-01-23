import re
from abc import ABC
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import ClassVar

from contextmodel import context_get, future_context_get
from githubkit import GitHub

SEP_RE = re.compile(r"\. \-_")
TRASH_CHARS_RE = re.compile(r"[^a-zA-Z\-]")
ISSUE_BRANCH_RE = re.compile(r"(?P<issue_number>\d{4,})(?P<slug>.+)")


class GitHubClient(GitHub):
    pass


def get_issue_name(client: GitHubClient, remote: Remote, number: int) -> str:
    match client.rest.issues.get(*remote, number).json():
        case {"title": title}:
            return title
    msg = f"invalid issue number {number}"
    raise ValueError(msg)


@dataclass
class Remote(ABC):
    owner: str
    repo: str
    site: str = "github.com"

    name: ClassVar[str]

    def __iter__(self) -> Iterator[str]:
        return iter((self.owner, self.repo))

    def ssh(self, git_user: str = "git") -> str:
        return f"{git_user}@{self.site}:{self.owner}/{self.repo}"

    def https(self, *, end_slash: bool = False) -> str:
        url = f"https://{self.site}/{self.owner}/{self.repo}"
        return url + ("/" if end_slash else "")


@dataclass
class Upstream(Remote):
    name = "upstream"


@dataclass
class Origin(Remote):
    name = "origin"


def get_slug_from_name(name: str) -> str:
    name = name.lower()
    name = SEP_RE.sub(" ", name)
    name = TRASH_CHARS_RE.sub(" ", name)
    name = name.replace("-", " ")
    words = sorted(set(name.split()), key=len, reverse=True)
    return "-".join(words[:5])  # type: ignore[no-matching-overload]


@dataclass
class Issue:
    number: int
    remote: Remote = field(default_factory=future_context_get(Upstream))

    @cached_property
    def url(self) -> str:
        return get_issue_url(self.remote, self.number)

    def fetch_name(self, client: GitHubClient | None = None) -> str:
        if client is None:
            client = context_get(GitHubClient)
        return get_issue_name(
            client=client,
            remote=self.remote,
            number=self.number,
        )

    def fetch_get_slug(self) -> str:
        return get_slug_from_name(self.fetch_name())

    def branch(self, slug: str, *, sep: str = "/") -> IssueBranch:
        return IssueBranch(f"{self.number}{sep and sep + slug}", upstream=self.remote)


@dataclass
class IssueBranch:
    name: str
    upstream: Remote

    @property
    def issue_number(self) -> int | None:
        match = ISSUE_BRANCH_RE.fullmatch(self.name)
        if not match:
            return None
        if number_as_str := match.group("issue_number"):
            return int(number_as_str)
        return None


@dataclass
class PullRequest:
    number: int
    remote: Remote = field(default_factory=future_context_get(Upstream))

    def fetch_needs_backport_to(
        self, version: str, github_client: GitHubClient | None = None
    ) -> bool:
        if github_client is None:
            github_client = context_get(GitHubClient)
        github_self = github_client.rest.pulls.get(
            self.remote.owner,
            self.remote.repo,
            self.number,
        ).json()
        label_names = {label["name"] for label in github_self["labels"]}
        return f"needs backport to {version}" in label_names


# /issues/ vs /pulls/ mostly doesn't matter, because GitHub
# redirects between these as necessary.


def get_issue_url(remote: Remote, number: int) -> str:
    return remote.https(end_slash=False) + f"/issues/{number}"


def get_pr_url(remote: Remote, number: int) -> str:
    return remote.https(end_slash=False) + f"/pulls/{number}"
