"""
GitHub Profile README Updater
Updates the Markdown README with age-based uptime.
"""

import datetime
import sys
import time

from dateutil.relativedelta import relativedelta


BIRTHDAY = "2005-06-06"


def daily_readme(birthday):
    diff = relativedelta(
        datetime.date.today(),
        datetime.datetime.strptime(birthday, "%Y-%m-%d").date(),
    )
    return f"{diff.years} years, {diff.months} months, {diff.days} days"


def readme_overwrite(filename, age):
    content = f"""## System

| Field | Value |
| --- | --- |
| OS | macOS |
| Host | UC3M / Computer Science |
| Shell | zsh |
| IDE | VS Code |
| Uptime | {age} |

## Languages

| Field | Value |
| --- | --- |
| Programming | Python, Bash, C, C++, RISC-V, HTML/CSS, JavaScript, TypeScript |
| Markup | HTML, CSS, Tailwind |
| Natural | Spanish, English |
"""
    with open(filename, "w") as f:
        f.write(content)


def main():
    t0 = time.time()
    print("Updating profile README...")

    age = daily_readme(BIRTHDAY)
    print(f"  Uptime: {age}")

    readme_overwrite("README.md", age)
    print("  Updated README.md")

    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"::error::{exc}")
        sys.exit(1)
