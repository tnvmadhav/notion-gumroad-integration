import json
import time
from http import HTTPStatus
from urllib.parse import urlparse

import requests
import yaml


class MyIntegration:

    def __init__(self):
        """
        Gets required variable data from config yaml file.
        """
        with open("my_variables.yml", 'r') as stream:
            try:
                self.my_variables_map = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print("[Error]: while reading yml file", exc)
        self.my_variables_map["NOTION_ENTRIES"] = {}
        self.getPageAndDatabaseData()
        self.getGumroadUserDetails()

    def getGumroadUserDetails(self):
        url = "https://api.gumroad.com/v2/user/"
        headers = {
            'Authorization': 'Bearer ' +
            self.my_variables_map["MY_GUMROAD_SECRET_TOKEN"],
        }
        response = requests.request("GET", url, headers=headers)
        if response.status_code == HTTPStatus.OK:
            self.my_variables_map["GUMROAD_USER"] = {
                "name": response.json()["user"]["name"],
                "profile": response.json()["user"]["url"]
            }

    def getPageAndDatabaseData(self):
        url = "https://api.notion.com/v1/databases/"
        headers = {
            'Notion-Version': '2021-05-13',
            'Authorization':
                'Bearer ' + self.my_variables_map["MY_NOTION_SECRET_TOKEN"]
        }
        response = requests.request("GET", url, headers=headers)
        self.my_variables_map["DATABASE_ID"] = \
            response.json()["results"][0]["id"]
        self.my_variables_map["PAGE_ID"] = \
            response.json()["results"][0]["parent"]["page_id"]
        # Database Entries
        url = f"https://api.notion.com/v1/databases/"\
              f"{self.my_variables_map['DATABASE_ID']}/query"
        response = requests.request("POST", url, headers=headers)
        resp = response.json()
        for v in resp["results"]:
            self.my_variables_map["NOTION_ENTRIES"].update({
                v["properties"]["Product Id"]["rich_text"][0]["plain_text"]: {
                    "Sales Count": v["properties"]["Sales Count"]["number"],
                    "Product": v["properties"]["Product"]
                    ["title"][0]["text"]["content"],
                    "Link": v["properties"]["Link"]["url"], "PageId": v["id"]
                }
            })

    def getGumroadProducts(self):
        url = "https://api.gumroad.com/v2/products/"
        headers = {
            'Authorization': 'Bearer ' +
            self.my_variables_map["MY_GUMROAD_SECRET_TOKEN"],
        }
        response = requests.request("GET", url, headers=headers)
        for i in response.json()["products"]:
            self.updateNotionEntries(i)

    def updateNotionEntries(self, data):
        for k, v in self.my_variables_map["NOTION_ENTRIES"].items():
            if data["id"] == k:
                v.update({
                    "Sales Count": data["sales_count"],
                    "Product": data["name"],
                    "Link": data["short_url"],
                    "Published": data["published"]
                })
                return
        self.my_variables_map["NOTION_ENTRIES"].update({
                data["id"]: {
                    "Sales Count": data["sales_count"],
                    "Product": data["name"],
                    "Link": data["short_url"],
                    "Published": data["published"]
                    }
                }
            )

    def updateNotionDatabase(self, pageId, databaseId, productId, data):
        if pageId:
            url = "https://api.notion.com/v1/pages/" + str(pageId)
            method = "PATCH"
        else:
            url = "https://api.notion.com/v1/pages/"
            method = "POST"
        headers = {
            'Authorization':
                'Bearer ' + self.my_variables_map["MY_NOTION_SECRET_TOKEN"],
            'Notion-Version': '2021-05-13',
            'Content-Type': 'application/json'
        }
        payload = json.dumps({
            "properties": {
                "Product Id": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": productId,
                            },
                            "plain_text": productId,
                        }
                    ]
                },
                "Sales Count": {
                    "number": data["Sales Count"]
                },
                "Link": {
                    "type": "url",
                    "url": data["Link"]
                },
                "Creator": {
                    "type": "url",
                    "url": urlparse(data["Link"]).netloc
                },
                "Published": {
                    "type": "checkbox",
                    "checkbox": data["Published"]
                },
                "Product": {
                    "title": [
                        {
                            "text": {
                                "content": data["Product"],
                            },
                            "plain_text": data["Product"],
                        }
                    ]
                }
            },
            "parent": {
                "type": "database_id",
                "database_id": databaseId,
            }
        })
        return requests.request(
                method, url, headers=headers, data=payload
            ).json()["id"]

    def updatePageTitle(self):
        """
        This is special!
        """
        sales = 0
        self.getPageAndDatabaseData()
        for _, data in self.my_variables_map["NOTION_ENTRIES"].items():
            sales += data["Sales Count"]
        url = f"https://api.notion.com/v1/pages/"\
              f"{self.my_variables_map['PAGE_ID']}"
        payload = json.dumps({
            "properties": {
                "title": {
                    "id": "title",
                    "type": "title",
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content":
                                f"👤 `{self.my_variables_map['GUMROAD_USER']['name']}`"
                                f" made {sales} Gumroad Product Sales",
                                "link": {
                                        "url": f"{self.my_variables_map['GUMROAD_USER']['profile']}"
                                    }
                            },
                        }
                    ]
                }
            }
        })
        headers = {
            'Notion-Version': '2021-05-13',
            'Authorization': 'Bearer ' + self.my_variables_map["MY_NOTION_SECRET_TOKEN"],
            'Content-Type': 'application/json'
        }
        requests.request("PATCH", url, headers=headers, data=payload)

    def UpdateIndefinitely(self):
        while True:
            try:
                self.getGumroadProducts()
                for productId, data in self.my_variables_map["NOTION_ENTRIES"].items():
                    print(data)
                    data["PageId"] = self.updateNotionDatabase(
                        pageId=data["PageId"] if "PageId" in data else None,
                        productId=productId,
                        data=data,
                        databaseId=self.my_variables_map["DATABASE_ID"]
                    )
                    time.sleep(5)
                self.updatePageTitle()
                time.sleep(10)
            except Exception as e:
                print(f"[Error encountered]: {e}")
                # Drop memory and rebuild from existing notion server state
                self.my_variables_map["NOTION_ENTRIES"] = {}
                self.getPageAndDatabaseData()


if __name__ == "__main__":
    # With 😴 sleeps to prevent rate limit from kicking in.
    MyIntegration().UpdateIndefinitely()
