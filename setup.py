#!/usr/bin/env python3
"""Setup script for BRING v2."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="bring-v2",
    version="2.0.0",
    author="BRING Team",
    description="Building Rich Interactive Narrative Games - AI-powered platform for persistent fantasy worlds",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Eva.E1/BRING",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Games/Entertainment :: Role-Playing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "faiss": ["faiss-cpu"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
        "web": [
            "fastapi>=0.104.0",
            "uvicorn[standard]>=0.24.0",
            "websockets>=12.0",
            "python-multipart>=0.0.6",
        ],
        "memory": [
            "faiss-cpu>=1.7.4",
            "sentence-transformers>=2.2.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "world=world_cli:main",
            "world-builder=world_builder.cli:app",
            "world-explorer=world_explorer.cli:app",
            "world-intelligence=world_intelligence.cli:app",
            "world-narrative=world_narrative.cli:app",
        ],
    },
)
