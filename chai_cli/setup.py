from setuptools import find_packages, setup

setup(
    name="chai-cli",
    version="0.1.0",
    description="Command-line client for the OpenCHAI GUI backend API",
    packages=find_packages(include=["chai", "chai.*"]),
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0,<9",
        "requests>=2.28,<3",
    ],
    extras_require={
        # Needed only for `chai logs follow`, `chai logs tail`, and --watch flags.
        "live": ["websockets>=11,<13"],
    },
    entry_points={
        "console_scripts": [
            "chai=chai.cli:main",
        ],
    },
)
