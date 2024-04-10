import base64
import os
from os.path import join, dirname
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import tempfile
import ffmpeg
import datetime
from pydub import AudioSegment
from pydub.silence import split_on_silence
import shutil
import tqdm

import sidemenu as side

# minutes
split_size = 10

load_dotenv(verbose=True)

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 環境変数からAPIキーを読み込む
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def __init__():
    st.session_state.shoq_hightlight_button=False
    st.session_state.show_submmit_form = False
    st.session_state.data = pd.DataFrame()

def init_page():
    st.set_page_config(page_title="ハイライト検出アプリ", page_icon="🎥", layout="centered", initial_sidebar_state="auto", menu_items=None)
    st.title("ハイライト検出アプリ")

def clear():
    st.session_state.shoq_hightlight_button=False
    st.session_state.show_submmit_form = False
    st.session_state.data = pd.DataFrame()
    
# ダウンロードリンクの生成
def create_download_link(file_path, download_name):
    with open(file_path, "rb") as f:
        bytes = f.read()
        b64 = base64.b64encode(bytes).decode()
        href = f'<a href="data:file/mp4;base64,{b64}" download="{download_name}">Download file</a>'
        return href


def cliping(start: float, end: float):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmpfile:
        tmpfile.write(st.session_state_audio.getvalue())

    # 一時ファイルに出力ファイルを保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as out_file:
        out_filename = out_file.name
    stream = ffmpeg.input(tmpfile.name, ss=start, t=end-start).output(out_filename)
    ffmpeg.run(stream, overwrite_output=True)

    # Streamlitにダウンロードリンクを表示
    st.markdown(create_download_link(out_filename, "download.mp4"), unsafe_allow_html=True)

def split_audio_file(file_path, segment_length, temp_dir):
    """
    音声ファイルを指定された長さで分割する。

    :param file_path: 分割するファイルのパス
    :param segment_length: 分割するセグメントの長さ（秒）
    :param temp_dir: 一時ディレクトリのパス
    :return: 分割されたファイルのパスのリスト
    """

    # 音声ファイルを読み込む
    audio = AudioSegment.from_file(file_path, format="mp4")

    # 分割するセグメントの長さをミリ秒に変換
    segment_length_ms = segment_length * 1000

    # 分割されたファイルのパスを格納するリスト
    split_files = []

    for i in range(0, len(audio), segment_length_ms):
        # 音声のセグメントを取得
        segment = audio[i:i + segment_length_ms]

        # 分割されたファイルのパスを生成
        segment_file_path = f"{temp_dir}/segment_{i // segment_length_ms}.mp4"

        # セグメントをファイルとして保存
        segment.export(segment_file_path, "mp4")

        # パスをリストに追加
        split_files.append(segment_file_path)

    return split_files


def wisper_transcript(file):
    with open(file, 'rb') as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json"
        )
    return transcript

def main():
    init_page()
    type = side.selectType()
    side.selectExtractType()
    audio_file = st.file_uploader(
        "音声ファイルをアップロードしてください", type=["m4a", "mp3", "webm", "mp4", "mpga", "wav"]
    )
    st.session_state_audio=audio_file
    
    if audio_file is not None:
        # st.audio(audio_file, format="audio/wav")
        st.video(audio_file)
        # 動画から文字起こしする
        # TODO でかいファイルには対応していないのでチャンク？する必要がある
        if st.button("音声文字起こしを実行する"):
            with st.spinner("音声文字起こしを実行中です..."):
                # タイムスタンプ付きの一時ディレクトリを作成
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                temp_dir = f'./{timestamp}_temp'
                os.makedirs(temp_dir, exist_ok=True)
                st.session_state.temp_dir = temp_dir
                # 分割の実行
                split_files = split_audio_file(audio_file, split_size * 60, st.session_state.temp_dir)  # 10分刻みに分割
                transcripts = [wisper_transcript(file) for file in split_files]
                # 一時ディレクトリの削除
                shutil.rmtree(st.session_state.temp_dir)
                
            st.success("音声文字起こしが完了しました！")
            filtered_data = []
            for i ,transcript in enumerate(transcripts):
                filtered_data.extend([
                        {
                        'start': str(item['start']+(i * split_size * 60)),  # timedeltaを秒数の文字列に変換します。
                        'end': str(item['end']+(i * split_size * 60)),  # timedeltaを秒数の文字列に変換します。
                        'content': item['text']
                        }
                        for item in transcript.segments
                ])
        
            st.session_state.whisper_data = filtered_data
            st.session_state.shoq_hightlight_button = True
            st.dataframe(pd.DataFrame(filtered_data))

        # 文字起こしされた字幕をハイライト分析
        if st.session_state.shoq_hightlight_button: 
            if st.button("ハイライト分析をする"):
                with st.spinner("ハイライト分析中です..."):
                    initial_prompt = (
                        f"あなたはスポーツの観戦中継から重要なシーンを字幕から判別することができます。今回の字幕データはサッカーの試合の字幕です。あなたがハイライトだと思ったシーンはhighlight!、そうでなかったらnotと答えてください。字幕は断片的に流れてきます。過去の結果を元に判断しても良いです。ハイライトと判定できなかったら一律でnotと答えて大丈夫です。' ")
                    # messages = [{"role": "system", "content": initial_prompt}]
                    h = []
                    for message in tqdm.tqdm(st.session_state.whisper_data):
                        
                        # messages.append({"role": "user", "content": message['content']})

                        res = client.chat.completions.create(
                            model="gpt-3.5-turbo", messages=[
                                {"role": "system", "content": initial_prompt},
                                {"role": "user", "content": f"start:{message['start']}, end:{message['end']}, message:{message['content']}"}
                            ]
                        )

                        # messages.append(
                        #     {"role": "assistant", "content": res.choices[0].message.content}
                        # )

                        h.append({
                            'start' : message['start'],
                            'end' : message['end'],
                            'content' : message['content'],
                            'isHighlight' : res.choices[0].message.content  
                        })
                st.success("分析が完了しました！")  
                st.session_state.data = pd.DataFrame(h)
                st.session_state.show_submmit_form = True
       
        if not st.session_state.data.empty :
            st.dataframe(st.session_state.data)

        # 時間指定して動画をクリッピングするモード
        if type == 0 and st.session_state.show_submmit_form:
            with st.form("my_form", clear_on_submit=False):
                start = st.text_input('開始時間を指定してください')
                end = st.text_input('終了時間を指定してください')
                submitted = st.form_submit_button("動画のクリッピング")
            if submitted:
                with st.spinner("動画をクリッピングしています..."):
                    cliping(float(start), float(end))
        
        # 自動的にハイライト動画をクリッピングするモード
        if type == 1 and st.session_state.show_submmit_form:
            if st.button("クリッピング"):
                counter = 0
                start = 0
                end = 0
                for is_highlight, start_time, end_time in zip(st.session_state.data['isHighlight'],st.session_state.data['start'],st.session_state.data['end']):
                    if(counter == 0 and is_highlight == 'highlight!'):
                        start = start_time
                        end = end_time
                        counter += 1
                    elif (counter > 0 and is_highlight == 'highlight!'):
                        end = end_time
                        counter += 1
                    elif (counter > 0 and is_highlight == 'not'):
                        cliping(float(start), float(end))
                        counter = 0
                        start = 0
                        end = 0
                
    else:
        clear()
        
if __name__ == '__main__':
    main()