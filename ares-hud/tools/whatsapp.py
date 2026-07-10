"""
Tool WhatsApp: invio di messaggi su WhatsApp Web tramite automazione del
browser (ricerca contatto, apertura chat, digitazione, invio).
"""
import subprocess
import time

from config import IS_MAC
from tools.browser import (
    focus_tab_matching,
    run_js_in_tab_matching,
    type_with_keystrokes,
    press_return_key,
)


def send_message(contact_name, message_text):
    """
    Cerca un contatto/gruppo su WhatsApp Web (che deve essere già aperto in una
    tab di Chrome) e gli invia un messaggio: cerca il nome, apre la prima chat
    trovata, digita il messaggio e preme Invio.
    Restituisce (True, None) se sembra andato a buon fine, oppure (False, motivo)
    dove motivo è uno tra: 'no_tab', 'no_search_box', 'no_results', 'no_compose_box'.
    """
    if not IS_MAC:
        return False, 'not_mac'

    if not focus_tab_matching('web.whatsapp.com'):
        return False, 'no_tab'
    time.sleep(0.4)

    focus_search_js = (
        "(function(){"
        "var input=document.querySelector('[data-testid=chat-list-search-container] input');"
        "if(!input){return 'NO_SEARCH';}"
        "input.focus();"
        "return 'OK';"
        "})();"
    )
    if run_js_in_tab_matching('web.whatsapp.com', focus_search_js) != 'OK':
        return False, 'no_search_box'

    time.sleep(0.2)
    # Pulisce eventuale ricerca precedente e digita il nome del contatto
    subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "a" using {command down}'], timeout=5)
    type_with_keystrokes(contact_name)
    time.sleep(0.9)  # tempo perché WhatsApp filtri i risultati

    click_result_js = (
        "(function(){"
        "var rows=document.querySelectorAll('[data-testid=cell-frame-container]');"
        "var visible=Array.from(rows).filter(function(r){return r.offsetParent!==null;});"
        "if(!visible.length){return 'NO_RESULTS';}"
        "var el=visible[0].closest('[role=listitem]')||visible[0];"
        "var rect=el.getBoundingClientRect();"
        "var opts={bubbles:true,cancelable:true,view:window,clientX:rect.left+rect.width/2,clientY:rect.top+rect.height/2,buttons:1};"
        "['pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(type){"
        "var Ctor=type.indexOf('pointer')===0?PointerEvent:MouseEvent;"
        "el.dispatchEvent(new Ctor(type,opts));"
        "});"
        "return 'OK';"
        "})();"
    )
    if run_js_in_tab_matching('web.whatsapp.com', click_result_js) != 'OK':
        return False, 'no_results'

    time.sleep(0.6)

    focus_compose_js = (
        "(function(){"
        "var footer=document.querySelector('footer');"
        "if(!footer){return 'NO_FOOTER';}"
        "var editable=footer.querySelector('[contenteditable=true]');"
        "if(!editable){return 'NO_EDITABLE';}"
        "editable.focus();"
        "return 'OK';"
        "})();"
    )
    if run_js_in_tab_matching('web.whatsapp.com', focus_compose_js) != 'OK':
        return False, 'no_compose_box'

    time.sleep(0.2)
    type_with_keystrokes(message_text)
    time.sleep(0.2)
    press_return_key()

    return True, None
