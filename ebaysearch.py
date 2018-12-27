import json
import requests

def parse_config():
    with open("config.json", "r") as f:
        configs = json.load(f)
        f.close()
    return configs

def push(item, configs):
    token = configs["pushover_token"]
    user_key = configs["pushover_user"]
    for i in item:
        pushTitle = i[0]
        url = i[2]
        url_title = i[1]
        post_data = 'token='+token+'&user='+user_key+'&title=eBay Alert for '\
                +pushTitle+'&message='+url_title+'&url='+url+'&url_title='+url_title
        post_data = str.encode(post_data)
        push_url = 'https://api.pushover.net/1/messages.json'
        requests.post(push_url, data=post_data)

def searchebay():
    configs = parse_config()
    appId = configs["appId"]
    session = requests.Session()
    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    session.headers = {
            "X-EBAY-SOA-SECURITY-APPNAME":appId,
            "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
            "X-EBAY-SOA-OPERATION-NAME": "findItemsByKeywords"
            } 
    items = [i for i in configs["items"]]
    for item in items:
        data = {"keywords":item}
        response = session.post(url, json=data).json()
        if int(response["findItemsByKeywordsResponse"][0]["paginationOutput"][0]["totalEntries"][0]) > 0:
            results = [
                    [item, k["title"][0], 
                    k["viewItemURL"][0], 
                    "${}".format(str(k["sellingStatus"][0]["currentPrice"][0]["__value__"]))]
                    for i in response["findItemsByKeywordsResponse"] 
                    for j in i["searchResult"] 
                    for k in j["item"]
                    ]
            push(results, configs)

searchebay()
