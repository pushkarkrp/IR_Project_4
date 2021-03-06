from textblob import TextBlob
import requests
import json
import re
import operator
import pandas as pd
import pickle
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from query_processor import Query_Processor

# CORE_NAME = "IRF21P4"
# AWS_IP = "18.118.132.49"

CORE_NAME = "IRF21P4"
AWS_IP = "18.118.132.49"

DIS_INFO_CORE_NAME = "DIS_INFO"
DIS_INFO_AWS_IP = "18.118.132.49"

query_processor = Query_Processor()

# CORE_NAME = "IRF21_class_demo"
# AWS_IP = "localhost"


def clean_tweet(tweet):
    return ' '.join(re.sub("(@[A-Za-z0-9]+)|([^0-9A-Za-z \t])|(\w+:\/\/\S+)", " ", str(tweet)).split())


def read_dummy_data_from_json():
    with open("data/dummy" + ".json", "r") as file:
        data = json.load(file)
    return data

'''
def get_tweet_sentiment(tweet):
    # create TextBlob object of passed tweet text
    text = clean_tweet(tweet['tweet_text'])
    analysis = TextBlob(text)
    if analysis.sentiment.polarity > 0:
        return 'positive', analysis.sentiment.polarity
    elif analysis.sentiment.polarity == 0:
        return 'neutral', analysis.sentiment.polarity
    else:
        return 'negative', analysis.sentiment.polarity


def transform_to_response(docs):
    response_tweets = []
    for doc in docs:
        sentiment_result, sentiment_score = get_tweet_sentiment(doc)
        doc['sentiment_result'] = sentiment_result
        doc['sentiment_score'] = sentiment_score
        response_tweets.append(doc)
    return response_tweets
'''

def get_stop_words(stop_file_path):
    with open(stop_file_path, 'r', encoding="utf-8") as f:
        stopwords = f.readlines()
        stop_set = set(m.strip() for m in stopwords)
        return frozenset(stop_set)


def sort(coo_matrix):
    tuples = zip(coo_matrix.col, coo_matrix.data)
    return sorted(tuples, key=lambda x: (x[1], x[0]), reverse=True)


def extract_topn_from_vector(feature_names, sorted_items, topn=10):
    """get the feature names and tf-idf score of top n items"""

    sorted_items = sorted_items[:topn]

    score_vals = []
    feature_vals = []

    for idx, score in sorted_items:
        fname = feature_names[idx]
        score_vals.append(round(score, 3))
        feature_vals.append(feature_names[idx])

    results = {}
    for idx in range(len(feature_vals)):
        results[feature_vals[idx]] = score_vals[idx]

    return results


def get_topics(data):
    data = pd.DataFrame(data)
    if (len(data) == 0): return {}
    data = data['tweet_text']
    print(data)

    try:
        if (type(data[0]) == list):
            data = [item for sublist in data for item in sublist]

        stopwords = get_stop_words("final_stopwords.txt")

        cv = CountVectorizer(max_df=0.85, stop_words=stopwords)
        word_count_vector = cv.fit_transform(data)

        tfidf_transformer = TfidfTransformer(smooth_idf=True, use_idf=True)
        tfidf_transformer.fit(word_count_vector)

        feature_names = cv.get_feature_names()

        doc = ' '.join(data)

        tf_idf_vector = tfidf_transformer.transform(cv.transform([doc]))

        sorted_items = sort(tf_idf_vector.tocoo())

        keywords = extract_topn_from_vector(feature_names, sorted_items, 20)

        topics_list = []

        for k in keywords:
            topics_dict = {}
            topics_dict['name'] = k
            topics_dict['weight'] = keywords[k]
            topics_list.append(topics_dict)

        return topics_list

    except Exception as e:
        return {}


def get_filter(field_name, value):
    return '&fq=' + field_name + '%3A' + value


def get_tweets_from_solr(query=None, country=None, poi_name=None, language=None, start=None, rows=None, return_raw_docs=False, field_exists=None, additional_filters = None, fetch_all = False):
    try:
        solr_url = 'http://{AWS_IP}:8983/solr/{CORE_NAME}'.format(AWS_IP=AWS_IP, CORE_NAME=CORE_NAME)

        if additional_filters != None and len(additional_filters) > 0:
            for filter in additional_filters:
                if 'dis_info' in filter:
                    solr_url = 'http://{AWS_IP}:8983/solr/{CORE_NAME}'.format(AWS_IP=DIS_INFO_AWS_IP, CORE_NAME=DIS_INFO_CORE_NAME)

        solr_url = solr_url + query_processor.get_query(query, field_exists)
        # solr_url = solr_url + '/select?q.op=OR&q=' + query + '&rows=20'

        if country is not None and country != '':
            solr_url = solr_url + get_filter('country', country)
        if poi_name is not None and poi_name != '':
            solr_url = solr_url + get_filter('poi_name', poi_name)
        if language is not None and language != '':
            solr_url = solr_url + get_filter('tweet_lang', language)

        if additional_filters is not None and len(additional_filters) > 0:
            for filter in additional_filters:
                if 'dis_info' not in filter:
                    field_name = filter.split(':')[0]
                    field_value = filter.split(':')[1]
                    solr_url = solr_url + get_filter(field_name, field_value)

        solr_url = solr_url + '&wt=json&indent=true'

        if start is not None and not fetch_all:
            solr_url = solr_url + '&start=' + str(start)
        if rows is not None and not fetch_all:
            solr_url = solr_url + '&rows=' + str(rows)
        print("Hitting Solr URL:", solr_url)
        docs = requests.get(solr_url)
        num_found = 0
        all_docs = []

        if docs.status_code == 200:
            docs = json.loads(docs.content)
            num_found = docs['response']['numFound']
            all_docs.extend(docs['response']['docs'])

            if fetch_all and len(all_docs) < num_found:
                start = len(all_docs) + 1
                rows = 2500
                while len(all_docs) < num_found:
                    updated_solr_url = solr_url + '&start=' + str(start)
                    updated_solr_url = updated_solr_url + '&rows=' + str(rows)
                    docs = requests.get(updated_solr_url)
                    docs = json.loads(docs.content)
                    all_docs.extend(docs['response']['docs'])

            print("Found ", str(num_found), "Docs")
            # docs = docs['response']['docs']
            if return_raw_docs == True:
                return all_docs, num_found
        else:
            all_docs = []
        # if docs is not None and len(docs.response.docs) != 0:
        #    docs = docs.response.docs

    except Exception as ex:
        print(ex)
        # all_docs = read_dummy_data_from_json()
        all_docs = []
        num_found = 0
    # tweet_response = transform_to_response(all_docs)
    return all_docs, num_found


def get_tweets_by_countries(query=None, country=None, poi_name=None, language=None, start=None, rows=None, additional_filters=None):
    tweets, num_found = get_tweets_from_solr(query, country, poi_name, language, start, rows, True, fetch_all=True, additional_filters=additional_filters)
    tweet_response = {
        "USA": 0,
        "INDIA": 0,
        "MEXICO": 0
    }
    for tweet in tweets:
        if tweet['country'] == 'USA':
            tweet_response["USA"] += 1
        elif tweet['country'] == 'INDIA':
            tweet_response["INDIA"] += 1
        elif tweet['country'] == 'MEXICO':
            tweet_response["MEXICO"] += 1
    return tweet_response


def get_tweets_by_sentiment(query=None, country=None, poi_name=None, language=None, start=None, rows=None, additional_filters=None):
    tweets, num_found = get_tweets_from_solr(query, country, poi_name, language, start, rows, False, fetch_all=True, additional_filters=additional_filters)
    tweet_response = {
        "positive": 0,
        "negative": 0,
        "neutral": 0
    }
    for tweet in tweets:
        if tweet['sentiment_result'] == 'positive':
            tweet_response["positive"] += 1
        elif tweet['sentiment_result'] == 'negative':
            tweet_response["negative"] += 1
        elif tweet['sentiment_result'] == 'neutral':
            tweet_response["neutral"] += 1
    return tweet_response


def get_replies_tweets_sentiment(query=None, start=None, rows=None, additional_filters=None):
    tweets, num_found = get_tweets_from_solr(query=query, start=start, rows=rows, field_exists='reply_text', fetch_all=True, additional_filters=additional_filters)
    negative_tweet = tweets[0]
    positive_tweet = tweets[0]
    tweet_response = {
        "positive": 0,
        "negative": 0,
        "neutral": 0
    }
    for tweet in tweets:
        if tweet['sentiment_result'] == 'positive':
            tweet_response["positive"] += 1
        elif tweet['sentiment_result'] == 'negative':
            tweet_response["negative"] += 1
        elif tweet['sentiment_result'] == 'neutral':
            tweet_response["neutral"] += 1
    for tweet in tweets:
        if tweet['sentiment_score'] > positive_tweet['sentiment_score']:
            positive_tweet = tweet
        if tweet['sentiment_score'] < negative_tweet['sentiment_score']:
            negative_tweet = tweet
    return tweet_response, positive_tweet, negative_tweet


def get_tweets_by_languages(query=None, country=None, poi_name=None, language=None, start=None, rows=None, additional_filters=None):
    tweets, num_found = get_tweets_from_solr(query, country, poi_name, language, start, rows, return_raw_docs=True, fetch_all=True, additional_filters=additional_filters)
    tweet_response = {
        "ENGLISH": 0,
        "HINDI": 0,
        "SPANISH": 0
    }
    for tweet in tweets:
        if tweet['tweet_lang'] == 'en':
            tweet_response["ENGLISH"] += 1
        elif tweet['tweet_lang'] == 'hi':
            tweet_response["HINDI"] += 1
        elif tweet['tweet_lang'] == 'es':
            tweet_response["SPANISH"] += 1
    return tweet_response


def get_top_hash_tags(query=None, country=None, poi_name=None, language=None, start=None, rows=None, additional_filters=None):
    tweets, num_found = get_tweets_from_solr(query, country, poi_name, language, start, 100, True, fetch_all=False, additional_filters=additional_filters)
    hashtags_by_freq = {}
    for tweet in tweets:
        if 'hashtags' not in tweet:
            continue
        hashtags = tweet['hashtags']
        count_frequency(hashtags, hashtags_by_freq)
    result = dict(sorted(hashtags_by_freq.items(), key=operator.itemgetter(1), reverse=True))
    top_10_hashtags = {}
    for key in result.keys():
        top_10_hashtags[key] = result[key]
        if len(top_10_hashtags) == 10:
            break
    return top_10_hashtags


def count_frequency(my_list, hashtags_by_freq):
    for item in my_list:
        if item in hashtags_by_freq:
            hashtags_by_freq[item] += 1
        else:
            hashtags_by_freq[item] = 1

# print(get_tweets_from_solr("covid",start=0, rows=10, field_exists='reply_text'))
