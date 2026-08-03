"""Sobe o Streamlit em segundo plano e abre uma janela nativa (pywebview) apontando para ele, sem terminal, sem navegador."""
import ctypes
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import webview

PORTA = 8765
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
APP_SCRIPT = BASE_DIR / "app.py"


def porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


def encontrar_porta_livre(porta_inicial: int) -> int:
    porta = porta_inicial
    while not porta_livre(porta):
        porta += 1
    return porta


def iniciar_servidor_streamlit(porta: int) -> None:
    from streamlit.web import bootstrap

    # O servidor roda numa thread secundária (a principal fica com o pywebview),
    # e signal.signal() só é permitido na thread principal do interpretador,
    # desativamos esse handler interno, já que o encerramento é feito ao fechar a janela 
    # (o processo inteiro termina e a thread daemon morre junto).
    bootstrap._set_up_signal_handler = lambda *args, **kwargs: None

    flag_options = {
        "server_port": porta,
        "server_address": "127.0.0.1",
        "server_headless": True,
        "browser_gatherUsageStats": False,
        "global_developmentMode": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(str(APP_SCRIPT), False, [], flag_options)


def aguardar_servidor(porta: int, tentativas: int = 100) -> bool:
    for _ in range(tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        threading.Event().wait(0.1)
    return False


def main() -> None:
    porta = encontrar_porta_livre(PORTA)

    thread_servidor = threading.Thread(
        target=iniciar_servidor_streamlit, args=(porta,), daemon=True
    )
    thread_servidor.start()

    aguardar_servidor(porta)

    # O pywebview desativa downloads por padrão na janela nativa (o clique no botão "Baixar Planilha" seria cancelado silenciosamente);
    # precisamos habilitar para que o diálogo "Salvar como" do Windows apareça.
    webview.settings["ALLOW_DOWNLOADS"] = True

    try:
        webview.create_window(
            "Regime Tributário — Consulta em Lote",
            f"http://127.0.0.1:{porta}",
            width=1360,
            height=860,
            min_size=(1000, 650),
        )
        webview.start()
    except Exception:
        # A janela nativa depende do WebView2/.NET Framework do Windows. Em alguns computadores
        # (ex: DLLs bloqueadas pelo Windows por terem vindo de uma pasta de rede/pendrive) essa inicialização falha. 
        # Em vez de travar com um erro no console, caímos para o navegador padrão, o app continua funcionando, só sem a janela própria.
        _abrir_no_navegador_padrao(porta)


def _abrir_no_navegador_padrao(porta: int) -> None:
    mensagem = (
        'Não foi possível abrir a janela do aplicativo neste computador.\n\n'
        'O programa vai abrir no seu navegador padrão em vez da janela própria.\n\n'
        'Para fechar o aplicativo depois, feche a aba do navegador e encerre o '
        'processo "RegimeTributario.exe" pelo Gerenciador de Tarefas.'
    )
    MB_ICONINFORMATION = 0x40
    ctypes.windll.user32.MessageBoxW(0, mensagem, "Regime Tributário", MB_ICONINFORMATION)

    webbrowser.open(f"http://127.0.0.1:{porta}")

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
