import time
import numpy as np
import os
import re
import datetime
import arxiv
import openai, tenacity
import base64, requests
import argparse
import configparser
import json
import tiktoken
import fitz, io, os
from PIL import Image


def download_pdf(url, file_name):
    response = requests.get(url)
    with open(file_name, 'wb') as file:
        file.write(response.content)
    print(f"PDF downloaded from {url} and saved as {file_name}")


class Paper:
    def __init__(self, path, title='', url='', abs='', authors=[]):       
        self.url =  url          
        self.path = path         
        self.section_names = []  
        self.section_texts = {}      
        self.abs = abs
        self.title_page = 0
        if title == '':
            self.pdf = fitz.open(self.path) 
            self.title = self.get_title()
            self.parse_pdf()            
        else:
            self.title = title
        self.authors = authors        
        self.roman_num = ["I", "II", 'III', "IV", "V", "VI", "VII", "VIII", "IIX", "IX", "X"]
        self.digit_num = [str(d+1) for d in range(10)]
        self.first_image = ''
        
    def parse_pdf(self):
        self.pdf = fitz.open(self.path) 
        self.text_list = [page.get_text() for page in self.pdf]
        self.all_text = ' '.join(self.text_list)
        self.section_page_dict = self._get_all_page_index()
        print("section_page_dict", self.section_page_dict)
        self.section_text_dict = self._get_all_page() 
        self.section_text_dict.update({"title": self.title})
        self.section_text_dict.update({"paper_info": self.get_paper_info()})
        self.pdf.close()    

    def get_paper_info(self):
        first_page_text = self.pdf[self.title_page].get_text()
        if "Abstract" in self.section_text_dict.keys():
            abstract_text = self.section_text_dict['Abstract']
        else:
            abstract_text = self.abs
        introduction_text = self.section_text_dict['Introduction']
        first_page_text = first_page_text.replace(abstract_text, "").replace(introduction_text, "")
        return first_page_text
        
    def get_image_path(self, image_path=''):
        # open file
        max_size = 0
        image_list = []
        with fitz.Document(self.path) as my_pdf_file:
            for page_number in range(1, len(my_pdf_file) + 1):
                page = my_pdf_file[page_number - 1]
                images = page.get_images()                
                for image_number, image in enumerate(page.get_images(), start=1):           
                    xref_value = image[0]
                    base_image = my_pdf_file.extract_image(xref_value)
                    image_bytes = base_image["image"]
                    ext = base_image["ext"]
                    image = Image.open(io.BytesIO(image_bytes))
                    image_size = image.size[0] * image.size[1]
                    if image_size > max_size:
                        max_size = image_size
                    image_list.append(image)
        for image in image_list:                            
            image_size = image.size[0] * image.size[1]
            if image_size == max_size:                
                image_name = f"image.{ext}"
                im_path = os.path.join(image_path, image_name)
                print("im_path:", im_path)
                
                max_pix = 480
                origin_min_pix = min(image.size[0], image.size[1])
                
                if image.size[0] > image.size[1]:
                    min_pix = int(image.size[1] * (max_pix/image.size[0]))
                    newsize = (max_pix, min_pix)
                else:
                    min_pix = int(image.size[0] * (max_pix/image.size[1]))
                    newsize = (min_pix, max_pix)
                image = image.resize(newsize)
                
                image.save(open(im_path, "wb"))
                return im_path, ext
        return None, None
    
    def get_chapter_names(self,):
        doc = fitz.open(self.path) 
        text_list = [page.get_text() for page in doc]
        all_text = ''
        for text in text_list:
            all_text += text
        chapter_names = []
        for line in all_text.split('\n'):
            line_list = line.split(' ')
            if '.' in line:
                point_split_list = line.split('.')
                space_split_list = line.split(' ')
                if 1 < len(space_split_list) < 5:
                    if 1 < len(point_split_list) < 5 and (point_split_list[0] in self.roman_num or point_split_list[0] in self.digit_num):
                        print("line:", line)
                        chapter_names.append(line)        
        
        return chapter_names
        
    def get_title(self):
        doc = self.pdf
        max_font_size = 0 
        max_string = "" 
        max_font_sizes = [0]
        for page_index, page in enumerate(doc): 
            text = page.get_text("dict") 
            blocks = text["blocks"] 
            for block in blocks: 
                if block["type"] == 0 and len(block['lines']):
                    if len(block["lines"][0]["spans"]):
                        font_size = block["lines"][0]["spans"][0]["size"]
                        max_font_sizes.append(font_size)
                        if font_size > max_font_size:
                            max_font_size = font_size
                            max_string = block["lines"][0]["spans"][0]["text"] 
        max_font_sizes.sort()                
        print("max_font_sizes", max_font_sizes[-10:])
        cur_title = ''
        for page_index, page in enumerate(doc):
            text = page.get_text("dict")
            blocks = text["blocks"]
            for block in blocks:
                if block["type"] == 0 and len(block['lines']):
                    if len(block["lines"][0]["spans"]):
                        cur_string = block["lines"][0]["spans"][0]["text"] 
                        font_flags = block["lines"][0]["spans"][0]["flags"]
                        font_size = block["lines"][0]["spans"][0]["size"]                     
                        if abs(font_size - max_font_sizes[-1]) < 0.3 or abs(font_size - max_font_sizes[-2]) < 0.3:                        
                            if len(cur_string) > 4 and "arXiv" not in cur_string:                            
                                if cur_title == ''    :
                                    cur_title += cur_string                       
                                else:
                                    cur_title += ' ' + cur_string                       
                            self.title_page = page_index
        title = cur_title.replace('\n', ' ')                        
        return title


    def _get_all_page_index(self):
        section_list = ["Abstract", 
                'Introduction', 'Related Work', 'Background', 
                "Preliminary", "Problem Formulation",
                'Methods', 'Methodology', "Method", 'Approach', 'Approaches',
                "Materials and Methods", "Experiment Settings",
                'Experiment',  "Experimental Results", "Evaluation", "Experiments",                        
                "Results", 'Findings', 'Data Analysis',                                                                        
                "Discussion", "Results and Discussion", "Conclusion",
                'References']
        section_page_dict = {}
        for page_index, page in enumerate(self.pdf):
            cur_text = page.get_text()
            for section_name in section_list:
                section_name_upper = section_name.upper()
                if "Abstract" == section_name and section_name in cur_text:
                    section_page_dict[section_name] = page_index
                else:
                    if section_name + '\n' in cur_text:
                        section_page_dict[section_name] = page_index
                    elif section_name_upper + '\n' in cur_text:
                        section_page_dict[section_name] = page_index
        return section_page_dict

    def _get_all_page(self):
        text = ''
        text_list = []
        section_dict = {}
        
        text_list = [page.get_text() for page in self.pdf]
        for sec_index, sec_name in enumerate(self.section_page_dict):
            print(sec_index, sec_name, self.section_page_dict[sec_name])
            if sec_index <= 0 and self.abs:
                continue
            else:
                start_page = self.section_page_dict[sec_name]
                if sec_index < len(list(self.section_page_dict.keys()))-1:
                    end_page = self.section_page_dict[list(self.section_page_dict.keys())[sec_index+1]]
                else:
                    end_page = len(text_list)
                print("start_page, end_page:", start_page, end_page)
                cur_sec_text = ''
                if end_page - start_page == 0:
                    if sec_index < len(list(self.section_page_dict.keys()))-1:
                        next_sec = list(self.section_page_dict.keys())[sec_index+1]
                        if text_list[start_page].find(sec_name) == -1:
                            start_i = text_list[start_page].find(sec_name.upper())
                        else:
                            start_i = text_list[start_page].find(sec_name)
                        if text_list[start_page].find(next_sec) == -1:
                            end_i = text_list[start_page].find(next_sec.upper())
                        else:
                            end_i = text_list[start_page].find(next_sec)                        
                        cur_sec_text += text_list[start_page][start_i:end_i]
                else:
                    for page_i in range(start_page, end_page):                    
                        if page_i == start_page:
                            if text_list[start_page].find(sec_name) == -1:
                                start_i = text_list[start_page].find(sec_name.upper())
                            else:
                                start_i = text_list[start_page].find(sec_name)
                            cur_sec_text += text_list[page_i][start_i:]
                        elif page_i < end_page:
                            cur_sec_text += text_list[page_i]
                        elif page_i == end_page:
                            if sec_index < len(list(self.section_page_dict.keys()))-1:
                                next_sec = list(self.section_page_dict.keys())[sec_index+1]
                                if text_list[start_page].find(next_sec) == -1:
                                    end_i = text_list[start_page].find(next_sec.upper())
                                else:
                                    end_i = text_list[start_page].find(next_sec)  
                                cur_sec_text += text_list[page_i][:end_i]
                section_dict[sec_name] = cur_sec_text.replace('-\n', '').replace('\n', ' ')
        return section_dict
                

class Reader:
    def __init__(self, key_word, query, filter_keys, 
                 root_path='./',
                 gitee_key='',
                 sort=arxiv.SortCriterion.SubmittedDate, user_name='defualt', args=None):
        self.user_name = user_name 
        self.key_word = key_word 
        self.query = query 
        self.sort = sort 
        self.language = 'English'        
        self.filter_keys = filter_keys
        self.root_path = root_path
        
        self.chat_api_list = [args.api_key]
        self.cur_api = 0
        self.file_format = args.file_format        
        
        self.max_token_num = 4096
        self.encoding = tiktoken.get_encoding("gpt2")
                
    def get_arxiv(self, max_results=30):
        search = arxiv.Search(query=self.query,
                              max_results=max_results,                              
                              sort_by=self.sort,
                              sort_order=arxiv.SortOrder.Descending,
                              )       
        return search
     
    def filter_arxiv(self, max_results=30):
        search = self.get_arxiv(max_results=max_results)
        print("all search:")
        for index, result in enumerate(search.results()):
            print(index, result.title, result.updated)
            print("abs_text:", result.summary.replace('-\n', '-').replace('\n', ' '))
            print("-"*30)
            
        filter_results = []   
        filter_keys = self.filter_keys
        
        print("filter_keys:", self.filter_keys)
        for index, result in enumerate(search.results()):
            abs_text = result.summary.replace('-\n', '-').replace('\n', ' ')
            meet_num = 0
            for f_key in filter_keys.split(" "):
                if f_key.lower() in abs_text.lower():
                    meet_num += 1
            if meet_num == len(filter_keys.split(" ")):
                filter_results.append(result)

        print("筛选后剩下的论文数量：")
        print("filter_results:", len(filter_results))
        print("filter_papers:")
        for index, result in enumerate(filter_results):
            print(index, result.title, result.updated)
        return filter_results
    
    def validateTitle(self, title):
        rstr = r"[\/\\:\*\?\"\<\>\|]" # '/ \ : * ? " < > |'
        new_title = re.sub(rstr, "_", title)
        return new_title

    def download_pdf(self, filter_results):
        date_str = str(datetime.datetime.now())[:13].replace(' ', '-')        
        key_word = str(self.key_word.replace(':', ' '))        
        path = self.root_path  + 'pdf_files/' + self.query.replace('au: ', '').replace('title: ', '').replace('ti: ', '').replace(':', ' ')[:25] + '-' + date_str
        try:
            os.makedirs(path)
        except:
            pass
        print("All_paper:", len(filter_results))
        paper_list = []
        for r_index, result in enumerate(filter_results):
            try:
                title_str = self.validateTitle(result.title)
                pdf_name = title_str+'.pdf'
                self.try_download_pdf(result, path, pdf_name)
                paper_path = os.path.join(path, pdf_name)
                print("paper_path:", paper_path)
                paper = Paper(path=paper_path,
                                url=result.entry_id,
                                title=result.title,
                                abs=result.summary.replace('-\n', '-').replace('\n', ' '),
                                authors=[str(aut) for aut in result.authors],
                              )
                paper.parse_pdf()
                paper_list.append(paper)
            except Exception as e:
                print("download_error:", e)
                pass
        return paper_list
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def try_download_pdf(self, result, path, pdf_name):
        result.download_pdf(path, filename=pdf_name)
        
    def summary_with_chat(self, paper_list):
        htmls = []
        for paper_index, paper in enumerate(paper_list):
            text = ''
            text += 'Title:' + paper.title
            text += 'Url:' + paper.url
            text += 'Abstrat:' + paper.abs
            text += 'Paper_info:' + paper.section_text_dict['paper_info']
            text += list(paper.section_text_dict.values())[0]
            
            chat_summary_text = self.chat_summary(text=text)            
            htmls.append('## Paper:' + str(paper_index+1))
            htmls.append('\n\n\n')            
            htmls.append(chat_summary_text)
            
            method_key = ''
            for parse_key in paper.section_text_dict.keys():
                if 'method' in parse_key.lower() or 'approach' in parse_key.lower():
                    method_key = parse_key
                    break
                
            if method_key != '':
                text = ''
                method_text = ''
                summary_text = ''
                summary_text += "" + chat_summary_text
                # methods                
                method_text += paper.section_text_dict[method_key]                   
                text = summary_text + "\n\n:\n\n" + method_text                 
                chat_method_text = self.chat_method(text=text)
                htmls.append(chat_method_text)
            else:
                chat_method_text = ''
            htmls.append("\n"*4)
            
            conclusion_key = ''
            for parse_key in paper.section_text_dict.keys():
                if 'conclu' in parse_key.lower():
                    conclusion_key = parse_key
                    break
            
            text = ''
            conclusion_text = ''
            summary_text = ''
            summary_text += "" + chat_summary_text + "\n :\n" + chat_method_text            
            if conclusion_key != '':
                # conclusion                
                conclusion_text += paper.section_text_dict[conclusion_key]                                
                text = summary_text + "\n\n:\n\n" + conclusion_text 
            else:
                text = summary_text            
            chat_conclusion_text = self.chat_conclusion(text=text)
            htmls.append(chat_conclusion_text)
            htmls.append("\n"*4)
            
            date_str = str(datetime.datetime.now())[:13].replace(' ', '-')
            try:
                export_path = os.path.join(self.root_path, 'export')
                os.makedirs(export_path)
            except:
                pass                             
            mode = 'w' if paper_index == 0 else 'a'
            file_name = os.path.join(export_path, date_str+'-'+self.validateTitle(paper.title)+"."+self.file_format)
            self.export_to_markdown("\n".join(htmls), file_name=file_name, mode=mode)
            
            htmls = []
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_conclusion(self, text):
        openai.api_key = self.chat_api_list[self.cur_api]
        self.cur_api += 1
        self.cur_api = 0 if self.cur_api >= len(self.chat_api_list)-1 else self.cur_api
        conclusion_prompt_token = 650        
        text_token = len(self.encoding.encode(text))
        clip_text_index = int(len(text)*(self.max_token_num-conclusion_prompt_token)/text_token)
        clip_text = text[:clip_text_index]   
        
        messages=[
                {"role": "system", "content": "You are a reviewer in the field of ["+self.key_word+"] and you need to critically review this article"},
                {"role": "assistant", "content": "This is the  and  part of an English literature, where  you have already summarized, but  part, I need your help to summarize the following questions:"+clip_text},
                {"role": "user", "content": """                 
                 8. Make the following summary.Be sure to use {} answers (proper nouns need to be marked in English).
                    - (1):What is the significance of this piece of work?
                    - (2):Summarize the strengths and weaknesses of this article in three dimensions: innovation point, performance, and workload.                   
                    .......
                 Follow the format of the output later: 
                 8. Conclusion: \n\n
                    - (1):xxx;\n                     
                    - (2):Innovation point: xxx; Performance: xxx; Workload: xxx;\n                      
                 
                 Be sure be as concise, helpful, and academic as possible, do not repeat the content of the previous, the value of the use of the original numbers, be sure to strictly follow the format, the corresponding content output to xxx, in accordance with \n line feed, ....... means fill in according to the actual requirements, if not, you can not write.                 
                 """.format(self.language, self.language)},
            ]
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("conclusion_result:\n", result)
        print("prompt_token_used:", response.usage.prompt_tokens,
              "completion_token_used:", response.usage.completion_tokens,
              "total_token_used:", response.usage.total_tokens)
        print("response_time:", response.response_ms/1000.0, 's')             
        return result            
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_method(self, text):
        openai.api_key = self.chat_api_list[self.cur_api]
        self.cur_api += 1
        self.cur_api = 0 if self.cur_api >= len(self.chat_api_list)-1 else self.cur_api
        text_token = len(self.encoding.encode(text))
        clip_text_index = int(len(text)*(self.max_token_num-args.method_prompt_token)/text_token)
        clip_text = text[:clip_text_index]        
        messages=[
                {"role": "system", "content": "You are a researcher in the field of ["+self.key_word+"] who is good at summarizing papers using concise statements"},  
                {"role": "assistant", "content": "This is the  and  part of an English document, where  you have summarized, but the  part, I need your help to read and summarize the following questions."+clip_text},
                {"role": "user", "content": """                 
                 7. Describe in detail the methodological idea of this article. Be sure to use {} answers (proper nouns need to be marked in English). For example, its steps are.
                    - (1):...
                    - (2):...
                    - (3):...
                    - .......
                 Follow the format of the output that follows: 
                 7. Methods: \n\n
                    - (1):xxx;\n 
                    - (2):xxx;\n 
                    - (3):xxx;\n  
                    ....... \n\n     
                 
                 Be sure to be as concise and academic as possible, do not repeat the content of the previous, the value of the use of the original numbers, be sure to strictly follow the format, the corresponding content output to xxx, in accordance with \n line feed, ....... means fill in according to the actual requirements, if not, you can not write.                 
                 """},
            ]
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("method_result:\n", result)
        print("prompt_token_used:", response.usage.prompt_tokens,
              "completion_token_used:", response.usage.completion_tokens,
              "total_token_used:", response.usage.total_tokens)
        print("response_time:", response.response_ms/1000.0, 's') 
        return result
    
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
                    stop=tenacity.stop_after_attempt(5),
                    reraise=True)
    def chat_summary(self, text):
        openai.api_key = self.chat_api_list[self.cur_api]
        self.cur_api += 1
        self.cur_api = 0 if self.cur_api >= len(self.chat_api_list)-1 else self.cur_api
        text_token = len(self.encoding.encode(text))
        clip_text_index = int(len(text)*(self.max_token_num-args.summary_prompt_token)/text_token)
        clip_text = text[:clip_text_index]
        messages=[
                {"role": "system", "content": "You are an expert researcher in the field of ["+self.key_word+"] who is excellent at summarizing papers using concise, helpful statements"},
                {"role": "assistant", "content": "This is the title, author, link, abstract and introduction of an English document. I need your help to read and summarize the following questions: "+clip_text},
                {"role": "user", "content": """                 
                 1. Mark the title of the paper
                 2. list all the authors' names
                 3. mark the first author's affiliation                
                 4. mark the keywords of this article 
                 5. link to the paper, Github code link (if available, fill in Github:None if not)
                 6. summarize according to the following four points.
                    - (1):What is the research background of this article?
                    - (2):What are the past methods? What are the problems with them? Is the approach well motivated?
                    - (3):What is the research methodology proposed in this paper?
                    - (4):On what task and what performance is achieved by the methods in this paper? Can the performance support their goals?
                 Follow the format of the output that follows: 
                 1. Title: xxx\n\n
                 2. Authors: xxx\n\n
                 3. Affiliation: xxx\n\n                 
                 4. Keywords: xxx\n\n   
                 5. Urls: xxx or xxx , xxx \n\n      
                 6. Summary: \n\n
                    - (1):xxx;\n 
                    - (2):xxx;\n 
                    - (3):xxx;\n  
                    - (4):xxx.\n\n     
                 
                 Be sure to be as concise and academic as possible, do not have too much repetitive information, numerical values using the original numbers. Be sure to strictly follow the format, the corresponding content output to xxx, in accordance with \n line feed.                 
                 """},
            ]
                
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )
        result = ''
        for choice in response.choices:
            result += choice.message.content
        print("summary_result:\n", result)
        print("prompt_token_used:", response.usage.prompt_tokens,
              "completion_token_used:", response.usage.completion_tokens,
              "total_token_used:", response.usage.total_tokens)
        print("response_time:", response.response_ms/1000.0, 's')                    
        return result        
                        
    def export_to_markdown(self, text, file_name, mode='w'):
        with open(file_name, mode, encoding="utf-8") as f:
            f.write(text)        

    def show_info(self):        
        print(f"Key word: {self.key_word}")
        print(f"Query: {self.query}")
        print(f"Sort: {self.sort}")                

def main(args):       
    if args.sort == 'Relevance':
        sort = arxiv.SortCriterion.Relevance
    elif args.sort == 'LastUpdatedDate':
        sort = arxiv.SortCriterion.LastUpdatedDate
    else:
        sort = arxiv.SortCriterion.Relevance

    if args.url:
        outpath = str(args.url).split('/')[-1]
        download_pdf(args.url, outpath)
        args.pdf_path = outpath
        
    if args.pdf_path and os.path.exists(args.pdf_path):
        reader1 = Reader(key_word=args.key_word, 
                    query=args.query, 
                    filter_keys=args.filter_keys,                                    
                    sort=sort, 
                    args=args
                )
        reader1.show_info()
        paper_list = []     
        if args.pdf_path.endswith(".pdf"):
            paper_list.append(Paper(path=args.pdf_path))            
        else:
            for root, dirs, files in os.walk(args.pdf_path):
                print("root:", root, "dirs:", dirs, 'files:', files)
                for filename in files:
                    if filename.endswith(".pdf"):
                        paper_list.append(Paper(path=os.path.join(root, filename)))        
        print("------------------paper_num: {}------------------".format(len(paper_list)))        
        [print(paper_index, paper_name.path.split('\\')[-1]) for paper_index, paper_name in enumerate(paper_list)]
        reader1.summary_with_chat(paper_list=paper_list)
    else:
        reader1 = Reader(key_word=args.key_word, 
                query=args.query, 
                filter_keys=args.filter_keys,                                    
                sort=sort, 
                args=args
                )
        reader1.show_info()
        filter_results = reader1.filter_arxiv(max_results=args.max_results)
        paper_list = reader1.download_pdf(filter_results)
        reader1.summary_with_chat(paper_list=paper_list)
    
    
if __name__ == '__main__':    
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_path", type=str, default='', help="if none, the bot will download from arxiv with query")
    parser.add_argument("--url", type=str, default='', help="Url to paper pdf to download.  Does not query ArXiv")
    parser.add_argument("--query", type=str, default='all: reinforcement learning', help="the query string, ti: xx, au: xx, all: xx,")
    parser.add_argument("--key_word", type=str, default='deep reinforcement learning', help="the key word of user research fields")
    parser.add_argument("--filter_keys", type=str, default='reinforcement learning', help="the filter key words")
    parser.add_argument("--max_results", type=int, default=2, help="the maximum number of results")
    parser.add_argument("--sort", type=str, default="Relevance", help="another is LastUpdatedDate, and Relevance")    
    parser.add_argument("--save_image", default=False, action='store_true', help="save image? It takes a minute or two to save a picture! But pretty")
    parser.add_argument("--file_format", type=str, default='md', help="Desired output format")
    parser.add_argument("--summary_prompt_token", type=int, default=1500, help="Number of tokens for content summary")
    parser.add_argument("--method_prompt_token", type=int, default=1000, help="Number of tokens for abstract summary")    
    parser.add_argument("--api_key", type=str, required=True, help="your openai api key!")
    args = parser.parse_args()
    start_time = time.time()
    main(args=args)    
    print("summary time:", time.time() - start_time)
         
