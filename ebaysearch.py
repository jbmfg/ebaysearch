import json
import requests
import shutil
import os
import base64
from datetime import datetime

def parse_config():
    with open("/home/jbg/dev/deals/ebaysearch/config.json", "r") as f:
        configs = json.load(f)
        f.close()
    return configs

def getImage(url):
    with open("image.jpg", "wb") as f:
        try:
            r = requests.get(url, stream=True)
        except requests.exceptions.MissingSchema:
            print("Image request failed")
            return os.path.abspath("/dev/null")
        r.raw.decode_content = True
        shutil.copyfileobj(r.raw, f)
    return os.path.abspath("image.jpg")

def push(item, listing_type):
    # Where sale_type is auction or fixed and item is a list of the details
    item_id, title, url, image_url, price, end_datetime, search_term, shipping = item
    configs = parse_config()
    token = configs["pushover_token"]
    user_key = configs["pushover_user"]
    image = getImage(image_url)
    files = {"attachment": ("image.jpg", open("image.jpg", "rb"), "image/jpeg")}
    message = f"Ends @ {end_datetime}\n{title}" if listing_type == "auction" else title
    post_data = {
            "token": token,
            "user": user_key,
            "title": f"({listing_type.upper()}) for {search_term} ${price} + {shipping}",
            "message": message,
            "url": url,
            "url_title": f"${price} + ${shipping}",
            "sound": "cashregister"
            }
    url = 'https://api.pushover.net/1/messages.json'
    requests.post(url, data=post_data, files=files)

def parse_search_response(search_response, search_term, shopping_token):
    # Take the search response and pull out the items we want to push
    search_response = search_response["findItemsAdvancedResponse"][0]
    result_count = search_response["paginationOutput"][0]["totalEntries"][0]
    results = {"auction": [], "fixed": []}
    if int(result_count) > 0:
        search_response_items = search_response["searchResult"][0]["item"]
        for response_item in search_response_items:
            item_id = response_item["itemId"][0]
            title = response_item["title"][0]
            url = response_item["viewItemURL"][0]
            image_url = response_item["galleryURL"][0]
            price = response_item["sellingStatus"][0]["convertedCurrentPrice"][0]["__value__"]
            price = '{:.2f}'.format(float(price))
            shipping = response_item["shippingInfo"][0]["shippingType"][0]
            if response_item["shippingInfo"][0]["shippingType"][0] == "Flat":
                if "shippingServiceCost" in response_item["shippingInfo"][0]:
                    shipping = response_item["shippingInfo"][0]["shippingServiceCost"][0]["__value__"]
                else:
                    shipping = 0.00
            elif response_item["shippingInfo"][0]["shippingType"][0] == "Calculated":
                shipping = get_shipping_cost(shopping_token, item_id)
            list_type = "auction" if response_item["listingInfo"][0]["listingType"][0] == "Auction" else "fixed"
            best_offer = response_item["listingInfo"][0]["bestOfferEnabled"][0]
            if best_offer == "true":
                price = f"{price} (OBO)"
            endtime = response_item["listingInfo"][0]["endTime"][0]
            results[list_type].append([item_id, title, url, image_url, price, endtime, search_term, shipping])
    return results

def get_token():
    configs = parse_config()
    client_id = configs["appId"]
    client_sec = configs["client_sec"]
    auth = base64.b64encode(bytes(f"{client_id}:{client_sec}", "utf-8")).decode()
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth}"
            }
    post_data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
            }

    r = requests.post(url, data=post_data, headers=headers)
    return r.json()["access_token"]

def get_shipping_cost(token, item_id):
    url = "https://open.api.ebay.com/shopping"\
    "?callname=GetShippingCosts"\
    "&responseencoding=JSON"\
    "&siteid=0"\
    "&version=517"\
    f"&ItemID={item_id}"\
    "&DestinationCountryCode=US"\
    "&DestinationPostalCode=04103"\
    "&IncludeDetails=true"\
    "&QuantitySold=1"
    headers = {"X-EBAY-API-IAF-TOKEN": token}
    r = requests.get(url, headers=headers)
    cost = r.json()["ShippingCostSummary"]["ShippingServiceCost"]["Value"]
    return cost

def setup_session():
    # Create session and set the correct headers
    session = requests.Session()
    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    app_id = parse_config()["appId"]
    session.headers = {
            "X-EBAY-SOA-SECURITY-APPNAME":app_id,
            "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
            "X-EBAY-SOA-OPERATION-NAME": "findItemsAdvanced"
            }
    return session

def get_searches():
    # open the config file and pull out the searches to perform
    configs = parse_config()
    search_terms = {
            "working": [i for i in configs["working_items"]],
            "parts": [i for i in configs["parts_items"]]
            }
    return search_terms

def search_ebay(session, search_item, condition):
    # where search_item is [search_term, category] and condition is either working or parts
    configs = parse_config()
    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    search_term, category = search_item
    data = {
            "keywords":search_term,
            "categoryId": str(category)
            }
    if condition == "parts":
        data["itemFilter"] = {"name": "Condition", "value": "7000"}
    elif condition == "working":
        data.pop("itemFilter", None)
    response = session.post(url, json=data)
    with open("benny.json", "w") as f:
        json.dump(response.json(), f)
    if response.status_code == 200:
        response = response.json()
    return response

def update_olds(new_item):
    # where new_item is the ebay id of the item to add to olds.json
    with open("/home/jbg/dev/deals/ebaysearch/old.json", "r") as f:
        data = json.load(f)
    data.append(new_item)
    with open("/home/jbg/dev/deals/ebaysearch/old.json", "w") as f:
        json.dump(data, f)

def main():
    session = setup_session()
    shopping_token = get_token()
    search_term_dict = get_searches()
    results = {"auction": [], "fixed": []}
    with open("/home/jbg/dev/deals/ebaysearch/old.json", "r") as f:
        olds = json.load(f)
    for condition in search_term_dict:
        for search_pair in search_term_dict[condition]:
            search_response = search_ebay(session, search_pair, condition)
            with open("results.json", "w") as f:
                json.dump(search_response, f)
            result = parse_search_response(search_response, search_pair[0], shopping_token)
            results["auction"] += result["auction"]
            results["fixed"] += result["fixed"]
    for sale_type in results:
        # Auction or Fixed
        for result in results[sale_type]:
            if result[0] not in olds:
                if sale_type == "fixed":
                    # just push as is
                    push(result, sale_type)
                    update_olds(result[0])
                elif sale_type == "auction":
                    # check to see if auction ends today then push if so
                    now = datetime.utcnow()
                    end_datetime = datetime.strptime(result[5], "%Y-%m-%dT%H:%M:%S.000Z")
                    if (end_datetime - now).days == 0:
                        end_time =  str((datetime.now() + (end_datetime-now)).time()).split(".")[0]
                        result[5] = end_time
                        push(result, sale_type)
                        update_olds(result[0])
    with open("/media/Storage/tmp/ebay_deals.json", "w") as f:
        json.dump(results, f)

if __name__ == "__main__":
    main()
