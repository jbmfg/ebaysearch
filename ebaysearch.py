import json
import requests
import shutil
import os
import base64
from time import sleep
from datetime import datetime

def parse_config():
    cwd = os.getcwd()
    with open(f"{cwd}/config.json", "r") as f:
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
    r = requests.post(url, data=post_data, files=files)

def push_digest(url="http://192.168.0.24/deals.html"):
    configs = parse_config()
    token = configs["pushover_token"]
    user_key = configs["pushover_user"]
    title = "Ebay deals ready to view"
    message = "Click for digest"
    post_data = {
            "token": token,
            "user": user_key,
            "title": title,
            "message": message,
            "url": url,
            "url_title": "Digest",
            "sound": "siren"
            }
    po_url = 'https://api.pushover.net/1/messages.json'
    sleep(10)
    r = requests.post(po_url, data=post_data)

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
            if search_term.lower() not in title.lower(): continue
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
    if response.status_code == 200:
        response = response.json()
    return response

def update_olds(new_item):
    # where new_item is the ebay id of the item to add to olds.json
    cwd = os.getcwd()
    config_path = f"{cwd}/old.json"
    with open(config_path, "r") as f:
        data = json.load(f)
    data.append(new_item)
    with open(config_path, "w") as f:
        json.dump(data, f)

def write_html(items):
    cols = {}
    for list_type in items:
        x = 0
        cols[list_type] = [[], [], [], []]
        for item_id, title, url, img, price, end_dt, search_term, shipping in items[list_type]:
            if x > 3: x = 0
            title = f"${price} + ${shipping} - {search_term}"
            cols[list_type][x].append(f'<a href="{url}"><img src="{img}" style="width:100%"></a><p>{title}</p>')
            #texts.append(f'<a href="{url}"><img src="{img}" style="width:100%"></a><p>{title}</p>')
            x += 1

    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
    }

    .header {
      text-align: center;
      padding: 32px;
    }

    .row {
      display: -ms-flexbox; /* IE 10 */
      display: flex;
      -ms-flex-wrap: wrap; /* IE 10 */
      flex-wrap: wrap;
      padding: 0 4px;
    }

    /* Create two equal columns that sits next to each other */
    .column {
      -ms-flex: 50%; /* IE 10 */
      flex: 50%;
      padding: 0 4px;
    }

    .column img {
      margin-top: 8px;
      vertical-align: middle;
    }

    /* Style the buttons */
    .btn {
      border: none;
      outline: none;
      padding: 10px 16px;
      background-color: #f1f1f1;
      cursor: pointer;
      font-size: 18px;
    }

    .btn:hover {
      background-color: #ddd;
    }

    .btn.active {
      background-color: #666;
      color: white;
    }
    </style>
    </head>
    <body>

    <!-- Header -->
    <div class="header" id="myHeader">
      <h1>JBG's Ebay Deals</h1>
      <p>Click on the buttons to change the grid view (Mobile only supports 2 columns)</p>
      <button class="btn" onclick="one()">1</button>
      <button class="btn" onclick="two()">2</button>
      <button class="btn active" onclick="four()">4</button>
    </div>

    <!-- Photo Grid -->
    """
    for list_type in ("fixed", "auction"):
        if list_type not in cols: continue
        html += f"""
        <div class="header" id="{list_type}">
        <h1>{list_type.title()}</h1>
        </div>
        <div class="row">
        """
        for col in cols[list_type]:
            html += '\n<div class="column">'
            for i in col:
                html += f'\n{i}'
            html += '</div>'
        html += '</div>'

    html += """
    <script>
    // Get the elements with class="column"
    var elements = document.getElementsByClassName("column");

    // Declare a loop variable
    var i;

    // Full-width images
    function one() {
        for (i = 0; i < elements.length; i++) {
        elements[i].style.msFlex = "100%";  // IE10
        elements[i].style.flex = "100%";
      }
    }

    // Two images side by side
    function two() {
      for (i = 0; i < elements.length; i++) {
        elements[i].style.msFlex = "50%";  // IE10
        elements[i].style.flex = "50%";
      }
    }

    // Four images side by side
    function four() {
      for (i = 0; i < elements.length; i++) {
        elements[i].style.msFlex = "25%";  // IE10
        elements[i].style.flex = "25%";
      }
    }

    // Add active class to the current button (highlight it)
    var header = document.getElementById("myHeader");
    var btns = header.getElementsByClassName("btn");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function() {
        var current = document.getElementsByClassName("active");
        current[0].className = current[0].className.replace(" active", "");
        this.className += " active";
      });
    }

    window.document.body.onload = four();
    </script>

    </body>
    </html>
    """
    with open("/var/www/localhost/htdocs/deals.html", "w") as f:
        f.write(html)

def main():
    session = setup_session()
    shopping_token = get_token()
    search_term_dict = get_searches()
    results = {"auction": [], "fixed": []}
    cwd = os.getcwd()
    with open(f"{cwd}/old.json", "r") as f:
        olds = json.load(f)
    for condition in search_term_dict:
        for search_pair in search_term_dict[condition]:
            search_response = search_ebay(session, search_pair, condition)
            with open("results.json", "w") as f:
                json.dump(search_response, f)
            result = parse_search_response(search_response, search_pair[0], shopping_token)
            results["auction"] += result["auction"]
            results["fixed"] += result["fixed"]
    digest = {}
    for sale_type in results:
        digest[sale_type] = []
        # Auction or Fixed
        for result in results[sale_type]:
            if result[0] not in olds:
                if sale_type == "fixed":
                    # just push as is
                    push(result, sale_type)
                    digest[sale_type].append(result)
                    update_olds(result[0])
                elif sale_type == "auction":
                    # check to see if auction ends today then push if so
                    now = datetime.utcnow()
                    end_datetime = datetime.strptime(result[5], "%Y-%m-%dT%H:%M:%S.000Z")
                    if (end_datetime - now).days == 0:
                        end_time =  str((datetime.now() + (end_datetime-now)).time()).split(".")[0]
                        result[5] = end_time
                        push(result, sale_type)
                        digest[sale_type].append(result)
                        update_olds(result[0])
    with open(f"{cwd}/ebay_deals.json", "w") as f:
        json.dump(results, f)
    write_html(digest)
    push_digest()

if __name__ == "__main__":
    main()
