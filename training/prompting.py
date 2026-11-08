"""Prompt format shared by training, offline evaluation and the service."""


def prompt(text):
    return f"Command: {text}\nJSON:"


def first_line(generated):
    """The model's answer is the first line it generates after 'JSON:'."""
    return generated.strip().split("\n", 1)[0].strip()
