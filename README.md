# edx-crawler

**edx-crawler** is a Python-based cross-platform tool for mining text data of the enrolled [edX](www.edx.org) courses available on a user's dashboard. It was developed by teaching assistants at Tokyo Tech Online Education Development Office as an extension of [edx-dl](https://github.com/coursera-dl/edx-dl).

## Prerequisites
Python libraries and modules:

* [Python](https://www.python.org/downloads/) - version 3.5+
* [beautifulsoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#installing-beautiful-soup) - a Python library for pulling data out of HTML and XML files
* [webvtt-py](https://pypi.python.org/pypi/webvtt-py) -  a Python module for reading/writing WebVTT caption files
* [youtube-dl](https://github.com/rg3/youtube-dl) - command-line program to download videos from YouTube.com

## How to run

Run a python script `edx_crawler.py` passing edx course link `-url` , username `-u` and password `-p` as parameters.

	python edx_crawler.py -url [course_url] -u [edx_user_name] -p [edx_user_password]

## OPTIONS

	-url, --course-urls		Specify target course urls given from edx dashboard
	-u, --username			Specify your edX username (email)
	-p, --password			Input your edX password
	-d, --html-dir			Specify directory to store data
	
The output is a weekly organized structure of the course, which is stored by default in "HTMLs" folder.
The output contents are the following:

* seq_contents_#.html - text data of the course unit in .html format
* seq_contents_#.txt - text data of the course unit in .txt format
* seq_contents_#_prob.txt - text data of the quiz sections in .txt format
* seq_contents_#_vdo.json - video transcript information in .json format

## Converting data to JSON format

After crawling courses, you may run `txtcomp2json.py` to store crawled data in .json format.

	python txtcomp2json.py
	
 The program aggregates crawled data of the courses in "HTMLs" folder and produces .json output in the following manner:
* all text components -> all_textcomp.json
* all problem components -> all_probcomp.json
* all video components -> all_videocomp.json
* all components (text, quizes, videos) -> all_comp.json

## Extra files and folders

transcript_error_report.txt contains the information about video transcripts which are not provided by edX or YouTube.
