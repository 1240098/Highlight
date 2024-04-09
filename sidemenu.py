import streamlit as st

def selectType():
    # サイドバーにオプションボタンを設置
    model = st.sidebar.radio("Choose a type:", ("auto", "manual clipping"))
    if model == "auto":
        return 1
    else :
        return 0

def selectExtractType():
    model = st.sidebar.radio("Highlight extraction type:", ("文字","音"))
    if model == "文字":
        return 1
    else :
        return 0