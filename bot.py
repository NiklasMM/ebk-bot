import logging
import sys

import click
import requests
from bs4 import BeautifulSoup
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater
from tinydb import Query, TinyDB

db = TinyDB("db.json")
Job = Query()

TELEGRAM_BOT_TOKEN = None


class JobExistsException(Exception):
    pass


def parse_result_item(item):
    """
    Takes a li item containing one search result and parses id, url and price from it.
    Returns a dict containing the results.
    """
    main = item.find_all("div", {"aditem-main"})
    price = item.find_all("p", {"aditem-main--middle--price"})
    article = item.find_all("article")

    if len(main) != 1 or len(article) != 1 or len(price) != 1:
        return
    main = main[0]
    article = article[0]
    price = price[0]

    result = {
        "ad_id": article["data-adid"],
        "price": price.text.strip(),
    }

    a = main.find_all("a")[0]
    result["url"] = "https://www.ebay-kleinanzeigen.de" + a["href"]

    return result


def execute_search(search_term):
    """
    Runs the search for one search term.
    Returns a list containing all parsed search results.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36"
    }
    url = f"https://www.ebay-kleinanzeigen.de/s-79249/{search_term}/k0l9364r20"

    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(response.content, features="html.parser")

    ul = soup.find_all("ul", {"id": "srchrslt-adtable"})
    assert len(ul) == 1

    ul = ul[0]

    items = ul.find_all("li")

    results = []
    for i in items:
        data = parse_result_item(i)
        if data is not None:
            results.append(data)
    if len(results) == 0:
        logging.warning(
            f"No results found for search term '{search_term}'. Check if parser works correctly."
        )
    return results


def init_search(search_term, chat_id):
    """
    Initialize a new search term.
    Executes one search and marks all current results as known.
    """
    result = db.search(Job.search_term == search_term)

    if result:
        raise JobExistsException

    initial_results = execute_search(search_term)
    ids = [_["ad_id"] for _ in initial_results]
    db.insert({"search_term": search_term, "chat_id": chat_id, "known_ads": ids})


def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)


def start_watching(update, context):
    """
    Command handler for starting to watch a new search term.
    """
    search_target = "".join(context.args)
    try:
        init_search(search_target, update.effective_chat.id)
    except JobExistsException:
        reply = "Hm, looks like I'm watching that already."
    else:
        reply = f"Ok, I'll start watching '{search_target}'"
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply)


def stop_watching(update, context):
    """
    Command handler for stopping to watch a search term
    """
    search_term = "".join(context.args)
    result = db.search(Job.search_term == search_term)

    if not result:
        reply = "I don't think I am watching that."
    else:
        db.remove(Job.search_term == search_term)
        reply = "Ok. I'll no longer watch " + search_term
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply)


def look_for_stuff(context):
    """
    Command handler to peridically check all active search jobs.
    """
    for job in db.all():
        known_ads = set(job["known_ads"])
        results = execute_search(job["search_term"])
        something_new = False
        for r in results:
            if r["ad_id"] not in known_ads:
                message = (
                    f"New item for {job['search_term']} ({r['price']}): {r['url']}"
                )
                context.bot.send_message(chat_id=job["chat_id"], text=message)
                known_ads.add(r["ad_id"])
                something_new = True

        if something_new:
            db.update(
                {"known_ads": list(known_ads)}, Job.search_term == job["search_term"]
            )
        else:
            # context.bot.send_message(chat_id=job["chat_id"], text=f"Nothing new for {job['search_term']}")
            pass


def status(update, context):
    message = "I'm currently watching: \n"
    for job in db.all():
        message += "- " + job["search_term"] + "\n"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--token", prompt=True, help="The telegram bot api token")
def run(token):
    TELEGRAM_BOT_TOKEN = token

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    job_queue = updater.job_queue

    job_minute = job_queue.run_repeating(look_for_stuff, interval=5 * 60, first=0)

    echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
    dispatcher.add_handler(echo_handler)

    start_watching_handler = CommandHandler("start", start_watching)
    dispatcher.add_handler(start_watching_handler)

    stop_handler = CommandHandler("stop", stop_watching)
    dispatcher.add_handler(stop_handler)

    status_handler = CommandHandler("status", status)
    dispatcher.add_handler(status_handler)

    updater.start_polling()


@cli.command()
@click.argument("searchterm")
def search(searchterm):
    data = execute_search(searchterm)
    click.echo(data)


if __name__ == "__main__":
    cli()
