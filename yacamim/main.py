#!/usr/bin/env python3

import cgi
import mailcap
import os
import socket
import ssl
import tempfile
import textwrap
import urllib.parse

caps = mailcap.getcaps()
menu = []
hist = []


def absolutise_url(base, relative):
    # Absolutise relative links
    if "://" not in relative:
        # Python's URL tools somehow only work with known schemes?
        base = base.replace("gemini://", "http://")
        relative = urllib.parse.urljoin(base, relative)
        relative = relative.replace("http://", "gemini://")
    return relative


def start():
    while True:
        cmd = input("> ").strip()
        # Handle things other than requests
        if cmd.lower() == "q":
            print("Boa viagem!")
            break
        # Get URL, from menu, history or direct entry
        if cmd.isnumeric():
            try:
                url = menu[int(cmd) - 1]
            except Exception as err:
                print("Error: ", err)
                print("Índice inválido, tente novamente")
                continue
        elif cmd.lower() == "b":
            url = hist.pop()
        else:
            url = cmd
            if not "://" in url:
                url = "gemini://" + url
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme != "gemini":
            print("Ops, apenas aceitamos links Gemini.")
            continue
        # Do the Gemini transaction
        try:
            while True:
                # Connect to a TCP service
                socket_object = socket.create_connection((parsed_url.netloc, 1965))
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                socket_object = context.wrap_socket(
                    socket_object, server_hostname=parsed_url.netloc
                )
                socket_object.sendall((url + "\r\n").encode("UTF-8"))
                # Get header and check for redirects
                fp = socket_object.makefile("rb")
                header = fp.readline()
                header = header.decode("UTF-8").strip()
                status, mime = header.split()
                # Handle input requests
                if status.startswith("1"):
                    # Prompt
                    query = input("INPUT" + mime + "> ")
                    url += "?" + urllib.parse.quote(query)
                # Follow redirects
                elif status.startswith("3"):
                    url = absolutise_url(url, mime)
                    parsed_url = urllib.parse.urlparse(url)
                # Otherwise, we're done.
                else:
                    break
        except Exception as err:
            print(err)
            continue
        # Fail if transaction was not successful
        if not status.startswith("2"):
            print("Error %s: %s" % (status, mime))
            continue
        # Handle text
        if mime.startswith("text/"):
            # Decode according to declared charset
            mime, mime_opts = cgi.parse_header(mime)
            body = fp.read()
            body = body.decode(mime_opts.get("charset", "UTF-8"))
            # Handle a Gemini map
            if mime == "text/gemini":
                menu = []
                preformatted = False
                for line in body.splitlines():
                    if line.startswith("```"):
                        preformatted = not preformatted
                    elif preformatted:
                        print(line)
                    elif line.startswith("=>") and line[2:].strip():
                        bits = line[2:].strip().split(maxsplit=1)
                        link_url = bits[0]
                        link_url = absolutise_url(url, link_url)
                        menu.append(link_url)
                        text = bits[1] if len(bits) == 2 else link_url
                        print("[%d] %s" % (len(menu), text))
                    else:
                        print(textwrap.fill(line, 80))
            # Handle any other plain text
            else:
                print(body)
        # Handle non-text
        else:
            tmpfp = tempfile.NamedTemporaryFile("wb", delete=False)
            tmpfp.write(fp.read())
            tmpfp.close()
            cmd_str, _ = mailcap.findmatch(caps, mime, filename=tmpfp.name)
            os.system(cmd_str)
            os.unlink(tmpfp.name)
        # Update history
        hist.append(url)
