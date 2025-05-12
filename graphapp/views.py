from django.shortcuts import render
from django.http import HttpResponse
import pdfplumber
import spacy
import networkx as nx
import textwrap
import matplotlib.pyplot as plt
import os
from django.conf import settings
import requests
from bs4 import BeautifulSoup
from newspaper import Article

nlp = spacy.load("en_core_web_sm")

def extract_text_from_pdf(pdf_file):
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def extract_text_from_url(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"Error extracting article: {str(e)}"

def input_form(request):
    if request.method == 'POST':
        input_type = request.POST.get('input_type')

        if input_type == 'pdf':
            pdf_file = request.FILES.get('pdf_file')
            if pdf_file:
                extracted_text = extract_text_from_pdf(pdf_file)
                graph_filename = 'knowledge_graph.png'
                graph_path = os.path.join(settings.MEDIA_ROOT, graph_filename)
                build_knowledge_graph(extracted_text, graph_path)
                graph_url = os.path.join(settings.MEDIA_URL, graph_filename)

           # Read the explanation .txt file
                graph_txt_path = graph_path.replace('.png', '.txt')
                explanation = ""
                if os.path.exists(graph_txt_path):
                     with open(graph_txt_path, 'r', encoding='utf-8') as f:
                       explanation = f.read()
                     return render(request, 'pdf_result.html', {'content': extracted_text, 'graph_url': graph_url, 'explanation': explanation,})


        elif input_type == 'url':
            url = request.POST.get('url')
            if url:
                extracted_text = extract_text_from_url(url)
                graph_filename = 'url_knowledge_graph.png'
                graph_path = os.path.join(settings.MEDIA_ROOT, graph_filename)
                build_knowledge_graph(extracted_text, graph_path)
                graph_url = os.path.join(settings.MEDIA_URL, graph_filename)
                return render(request, 'url_result.html', {'url': url, 'content': extracted_text, 'graph_url': graph_url,})
        
        elif input_type == 'context':
            content = request.POST.get('content')
            if content:
             graph_filename = 'context_knowledge_graph.png'
             graph_path = os.path.join(settings.MEDIA_ROOT, graph_filename)
             build_knowledge_graph(content, graph_path)
             graph_url = os.path.join(settings.MEDIA_URL, graph_filename)

        # Load explanation
             explanation = ""
             graph_txt_path = graph_path.replace('.png', '.txt')
             if os.path.exists(graph_txt_path):
              with open(graph_txt_path, 'r', encoding='utf-8') as f:
                 explanation = f.read()

             return render(request, 'context_result.html', {'content': content,'graph_url': graph_url,'explanation': explanation,
        })

    return render(request, 'input_form.html')

def build_knowledge_graph(text, output_path):
    import os
    import spacy
    import matplotlib.pyplot as plt
    import networkx as nx

    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)

    # Combine named entities and compound proper nouns
    phrases = []
    skip = set()
    for ent in doc.ents:
        phrases.append((ent.start, ent.end, ent.text))

    for i, token in enumerate(doc):
        if token.pos_ == "PROPN" and i not in skip:
            j = i + 1
            while j < len(doc) and doc[j].pos_ == "PROPN":
                j += 1
            if j > i + 1:
                phrase = " ".join([t.text for t in doc[i:j]])
                phrases.append((i, j, phrase))
                skip.update(range(i, j))

    phrases = sorted(phrases, key=lambda x: x[0])

    # Merge tokens into phrases
    merged_tokens = []
    idx = 0
    while idx < len(doc):
        for start, end, phrase in phrases:
            if idx == start:
                merged_tokens.append((phrase, doc[start].pos_))
                idx = end
                break
        else:
            token = doc[idx]
            merged_tokens.append((token.text, token.pos_))
            idx += 1

    # Remove unwanted parts of speech
    allowed_pos = {"NOUN", "PROPN"}
    helping_verbs = {
        "is", "am", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "shall", "should", "can", "could", "may", "might", "must"
    }
    stop_words = {"news", "day", "best", "latest", "today", "top"}

    # Custom list of titles/honorifics to exclude
    honorifics = {"mr", "mrs", "ms", "dr", "prof", "sir", "madam", "captain", "colonel", "shri", "smt"}

    filtered = [
        (w, p) for w, p in merged_tokens
        if p in allowed_pos
        and w.lower() not in helping_verbs
        and w.lower() not in stop_words
        and w.lower() not in honorifics
        and len(w) > 2
        and p not in {"PRON", "DET"}
    ]

    # Limit to top 75 tokens to reduce clutter
    MAX_NODES = 75
    filtered = filtered[:MAX_NODES]

    # Build directed graph
    G = nx.DiGraph()
    subjects = set()

    for i in range(len(filtered) - 1):
        src, src_pos = filtered[i]
        tgt, tgt_pos = filtered[i + 1]
        G.add_edge(src, tgt)
        subjects.add(src)

    # ENTITY COLORS + POSITIONS
    entity_colors = {
        "PERSON": "lightgreen",
        "GPE": "lightskyblue",
        "LOC": "deepskyblue",
        "ORG": "plum",
        "WORK_OF_ART": "moccasin"
    }

    # Entity priority for positioning
    entity_priority = {
        "PERSON": 1,
        "GPE": 2,
        "LOC": 2,
        "ORG": 3,
        "WORK_OF_ART": 4
    }

    # Lookup for node types
    entity_lookup = {ent.text: ent.label_ for ent in doc.ents}

    # Assign colors and manual positions
    node_colors = []
    node_sizes = []
    pos = {}
    x = 0.5
    default_color = "lightsalmon"  # ✅ safe fallback color
    sorted_nodes = sorted(G.nodes(), key=lambda n: entity_priority.get(entity_lookup.get(n, ""), 5))
    for i, node in enumerate(sorted_nodes):
        ent_type = entity_lookup.get(node, "")
        color = entity_colors.get(ent_type, default_color)
        y = 1 - (entity_priority.get(ent_type, 5) * 0.2)  # Higher priority at top       
        row = i // 18
        col = i % 18
        pos[node] = (x + col * 2, y - row * 1)
        node_colors.append(color)
        node_sizes.append(1000 + len(node) * 100)


    # Draw graph
    import textwrap
    wrapped_labels = {}
    for node in G.nodes():
       wrapped_labels[node] = '\n'.join(textwrap.wrap(node, width=20))
    plt.figure(figsize=(28, 28))
    nx.draw(
        G, pos,
        labels=wrapped_labels,
        with_labels=True,
        node_color=node_colors,
        edge_color='black',
        node_size=node_sizes,
        font_size=15,
        arrows=True,
        arrowstyle='->',
        arrowsize=25
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()

    # Save explanation
    explanation_path = output_path.replace('.png', '.txt')
    explanation_lines = [f"'{src}' is related to '{tgt}'." for src, tgt in G.edges()]
    with open(explanation_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(explanation_lines))


