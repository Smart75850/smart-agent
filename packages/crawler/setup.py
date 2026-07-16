from setuptools import setup, find_packages
setup(
    name="smart-crawler",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["playwright>=1.40", "curl_cffi>=0.6", "httpx>=0.25"],
    python_requires=">=3.9",
)
