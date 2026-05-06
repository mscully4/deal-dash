import pytest


@pytest.fixture
def sample_api_response():
    return {
        "found": 2,
        "hits": [
            {
                "title": "Padlock Steel 2in",
                "price": 1.17,
                "discount": 91,
                "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F123",
                "category": "Hardware",
                "stock": 3,
            },
            {
                "title": "Impact Bit Set",
                "price": 4.48,
                "discount": 95,
                "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F456",
                "category": "Tools",
                "stock": 1,
            },
        ],
    }
