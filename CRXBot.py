#!/usr/bin/env python3

import json
import os
import requests
import sys
import tweepy
import time
from datetime import datetime

doiRootURL = "https://doi.org/"

def write_log(message):
    print(message)
    with open('activity_log.txt', 'a') as f:
        f.write(str(datetime.now()) + ' ' + message + '\n')

def tweet_image(url, message):
    ###Takes in a file from a URL, downloads it,
    ###tweets it with the given message, then deletes the file
    filename = 'temp.jpg'
    request = requests.get(url, stream=True)
    if request.status_code == 200:
        with open(filename, 'wb') as image:
            for chunk in request:
                image.write(chunk)

        twitter_api.update_with_media(filename, status=message)
        os.remove(filename)
        write_log(f'Tweet successful. {message}')
    else:
        write_log("Error, couldn't download image.")

def prepare_tweet(title, author, preprintURL):
    ## Tweet format : {TITLE} by {AUTHOR} \n {DOI URL} [thumbnail image]

    tweetText = f'{title} by {author} & co-workers' + "\n\n" + preprintURL

    ## Need to make sure the total length of the tweet is <280 characters

    if len(tweetText) >= 280:
        write_log('Tweet text too long; cannot continue')
        return False
    else:
        return tweetText

    ## For authors, enumerated as a list of dictionaries. Relevant key is full_name
    ## Possible to assess whether all authors can fit before deciding which to tweet?
    ## First author is not always appropriate, but neither is last.
    ## Going to start by just tweeting the last author and developing as needed

class chemRxivAPI:
    ## Class taken from FX Coudert's ChemRxiv.py https://github.com/fxcoudert

    """Handle figshare API requests, using access token"""

    base = 'https://api.figshare.com/v2'
    pagesize = 100

    def __init__(self, token):
        """Initialise the object and check access to the API"""

        self.token = token
        self.headers = {'Authorization': 'token ' + self.token}

        r = requests.get(f'{self.base}/account', headers=self.headers)
        r.raise_for_status()

    def request(self, url, method, params):
        """Send a figshare API request"""

        if method.casefold() == 'get':
            return requests.get(url, headers=self.headers, params=params)
        elif method.casefold() == 'post':
            return requests.post(url, headers=self.headers, json=params)
        else:
            raise Exception(f'Unknown method for query: {method}')

    def query(self, query, method='get', params=None):
        """Perform a direct query"""

        r = self.request(f'{self.base}/{query}', method, params)
        r.raise_for_status()
        return r.json()

    def query_generator(self, query, method='get', params={}):
        """Query for a list of items, with paging. Returns a generator."""

        n = 0
        while True:
            params.update({'limit': self.pagesize, 'offset': n})
            r = self.request(f'{self.base}/{query}', method, params)
            r.raise_for_status()
            r = r.json()

            # Special case if a single item, not a list, was returned
            if not isinstance(r, list):
                yield r
                return

            # If we have no more results, bail out
            if len(r) == 0:
                return

            yield from r
            n += self.pagesize

    def query_list(self, *args, **kwargs):
        """Query of a list of item, handling paging internally, returning a
        list. May take a long time to return."""

        return list(self.query_generator(*args, **kwargs))

    def all_preprints(self):
        """Return a generator to all the chemRxiv preprints"""

        return api.query_generator('articles?institution=259')

    def preprint(self, identifier):
        """Information on a given preprint"""

        return api.query(f'articles/{identifier}')

    def author(self, identifier):
        """Information on a given preprint"""

        return api.query(f'account/authors/{identifier}')

    def custom_fields_as_dict(self, doc):
        """Retrieve chemRxiv custom fields as a dictionary"""

        return {i['name']: i['value'] for i in doc['custom_fields']}

    def search_authors(self, criteria):
        """Search for authors"""

        return api.query('account/authors/search', method='POST', params=criteria)

    def search_preprints(self, criteria):
        """Search for preprints"""

        p = {**criteria, 'institution': 259}
        return api.query_list('articles/search', method='POST', params=p)



###############################################################
##                      START UP ROUTINES                    ##
###############################################################

## Pull in keys

# Store keys, secrets & tokens in CRX_keys.text
# Format the file like this, with no additional text in the document:
# twitKey
# twitSecret
# twitToken
# twitToken_secret
# chemRxiv_token

## Read in CRX_keys.txt as a list
CRX_keys = []
with open('CRX_keys.txt', 'r') as f:
    CRX_keys = list(f)

#clean up the keys
for i in range(len(CRX_keys)):
    temp = CRX_keys[i]
    CRX_keys[i] = temp.strip('\n')
write_log("Keys, tokens and secrets successfully loaded...")

twitKey = CRX_keys[0]
twitSecret = CRX_keys[1]
twitToken = CRX_keys[2]
twitToken_secret = CRX_keys[3]
chemRxiv_token = CRX_keys[4]

## Prep Twitter
twitter_auth = tweepy.OAuthHandler(twitKey, twitSecret)
twitter_auth.set_access_token(twitToken, twitToken_secret)
twitter_api = tweepy.API(twitter_auth)
twitterUser = twitter_api.me().screen_name
write_log(f'Authenticated as Twitter user {twitterUser} successfully.')

## Connect to Figshare
try:
    api = chemRxivAPI(chemRxiv_token)
except requests.exceptions.HTTPError as e:
    write_log(f'Authentication did not succeed. Token was: {token}')
    write_log(f'Error: {e}')
    sys.exit(1)
write_log("Authenticated with Figshare.")

## Read in the ID Log as a list
id_log = []
with open('id_log.txt', 'r') as f:
    id_log = list(f)

#clean up the id_log
for i in range(len(id_log)):
    temp = id_log[i]
    id_log[i] = temp.strip('\n')
write_log("ID Log successfully loaded...")

###############################################################
##                      BOT STARTS HERE                      ##
###############################################################

# pull down preprints
doc = api.all_preprints()
numberPreprints = sys.getsizeof(doc)
write_log(f'Retrieved {numberPreprints} preprints. Beginning search for new content...')

preprints_added = 0
preprints_tweeted = 0
preprints_tweeted_FAILED = 0

# iterate through the preprints

for i in range(numberPreprints):
        # load preprint data
        l = next(doc)

        preprint_id = str(l['id'])


        # only proceed if the preprint has not been processed previously
        if preprint_id in id_log:
            pass
        else:
            write_log("New preprint found!")

            ## Pull the full dataset for the preprint
            ## (for some reason the general pull doesn't
            ## get the author information, so let's only
            ## enumerate this for preprints we're going to
            ## actually tweet)

            current_preprint = api.preprint(preprint_id)

            ## Collect the information needed for the tweet

            preprint_title = current_preprint['title']

            ## Extracting the author data takes a bit more work
            authorData = current_preprint['authors']
            lastAuthorData = authorData[-1]

            ## This is the variable to pass to the tweet preparer
            preprintAuthor = lastAuthorData['full_name']

            ## Format the URL based off of the doi

            preprintURL = doiRootURL + current_preprint['doi']

            ## Grab the thumbnail url

            thumbnailURL = current_preprint['thumb']

            ## Prepare the tweet; throw an error if it it's too long
            ## Future note: what should we do when they are too long?
            ## How often will that happen? Should it notify me somehow?
            ## Let's wait and see...

            tweetText = prepare_tweet(preprint_title, preprintAuthor, preprintURL)

            if tweetText == False:
                write_log(f'NOTICE: Could not tweet preprint at {preprintURL}, please check manually.')
                preprints_tweeted_FAILED += 1
            else:
                write_log(f'Submitting {preprint_id} to Twitter...')
                tweet_image(thumbnailURL, tweetText)
                preprints_tweeted += 1


            write_log("Committing ID to log...")
            with open('id_log.txt', 'a') as f:
                f.write(preprint_id + '\n')
            write_log(f'Wrote {current_preprint["id"]} to log')
            preprints_added += 1
            time.sleep(30) # Currently set to wait 30 sec after each tweet for testing purposes. Should be increased when running for real (likely to 1800).
            ## Need to set a better solution for looping through the script. Considering Daemon or Cron
write_log(f'All preprints checked. Processed {preprints_added} new preprints. Tweeted {preprints_tweeted}, failed to tweet {preprints_tweeted_FAILED}.')
