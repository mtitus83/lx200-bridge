import socket
import requests
import time

HOST = "0.0.0.0"
PORT = 10001

ALPACA = "http://127.0.0.1:5555"
DEVICE = 1

CLIENT_ID = 1
TX = 0

target_ra = None
target_dec = None


# -----------------------------
# Alpaca helpers
# -----------------------------

def alpaca_get(endpoint):

    global TX
    TX += 1

    try:

        r = requests.get(
            f"{ALPACA}{endpoint}",
            params={
                "ClientID": CLIENT_ID,
                "ClientTransactionID": TX
            },
            timeout=5
        )

        return r.json()["Value"]

    except Exception as e:

        print("ALPACA GET ERROR:", e)
        return None


def alpaca_put(endpoint, payload):

    global TX
    TX += 1

    payload |= {
        "ClientID": CLIENT_ID,
        "ClientTransactionID": TX
    }

    try:

        r = requests.put(
            f"{ALPACA}{endpoint}",
            data=payload,
            timeout=5
        )

        print("ALPACA:", r.text)

    except Exception as e:

        print("ALPACA PUT ERROR:", e)


# -----------------------------
# Coordinate helpers
# -----------------------------

def ra_to_hours(ra):

    h, m, s = map(float, ra.split(":"))
    return h + m/60 + s/3600


def dec_to_deg(dec):

    dec = dec.replace("*", ":")
    sign = -1 if dec.startswith("-") else 1

    dec = dec.replace("+", "").replace("-", "")

    d, m, s = map(float, dec.split(":"))

    return sign * (d + m/60 + s/3600)


def hours_to_ra(hours):

    if hours is None:
        return b"00:00:00#"

    h = int(hours)
    m = int((hours-h)*60)
    s = int(((hours-h)*60-m)*60)

    return f"{h:02}:{m:02}:{s:02}#".encode()


def deg_to_dec(deg):

    if deg is None:
        return b"+00*00:00#"

    sign = "+" if deg >= 0 else "-"

    deg = abs(deg)

    d = int(deg)
    m = int((deg-d)*60)
    s = int(((deg-d)*60-m)*60)

    return f"{sign}{d:02}*{m:02}:{s:02}#".encode()


# -----------------------------
# Mount helpers
# -----------------------------

def ensure_unparked():

    try:

        parked = alpaca_get(
            f"/api/v1/telescope/{DEVICE}/atpark"
        )

        if parked:

            print("Mount parked → unparking")

            alpaca_put(
                f"/api/v1/telescope/{DEVICE}/unpark",
                {}
            )

            time.sleep(2)

    except Exception as e:

        print("UNPARK ERROR:", e)


# -----------------------------
# Slew telescope
# -----------------------------

def slew():

    global target_ra, target_dec

    if not target_ra or not target_dec:
        return

    ensure_unparked()

    try:

        ra = ra_to_hours(target_ra)
        dec = dec_to_deg(target_dec)

        print("SLEW:", ra, dec)

        alpaca_put(
            f"/api/v1/telescope/{DEVICE}/slewtocoordinates",
            {
                "RightAscension": ra,
                "Declination": dec
            }
        )

    except Exception as e:

        print("SLEW ERROR:", e)


# -----------------------------
# Start server
# -----------------------------

print(f"LX200 bridge listening on {PORT}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen(5)


while True:

    conn, addr = server.accept()

    print("Client connected:", addr)

    buffer = b""

    try:

        while True:

            data = conn.recv(1024)

            if not data:
                break

            print("RAW:", data)

            # LX200 ACK probe
            if b"\x06" in data:
                conn.sendall(b"A")
                continue

            # Stellarium probe
            if data.startswith(b"Ka"):
                conn.sendall(b"1")
                continue

            buffer += data

            while b"#" in buffer:

                cmd, buffer = buffer.split(b"#", 1)

                cmd = cmd.decode(errors="ignore").strip()

                if not cmd:
                    continue

                print("LX200:", cmd)

                # Get RA
                if cmd == ":GR":

                    ra = alpaca_get(
                        f"/api/v1/telescope/{DEVICE}/rightascension"
                    )

                    conn.sendall(hours_to_ra(ra))

                # Get DEC
                elif cmd == ":GD":

                    dec = alpaca_get(
                        f"/api/v1/telescope/{DEVICE}/declination"
                    )

                    conn.sendall(deg_to_dec(dec))

                # Set RA
                elif cmd.startswith(":Sr"):

                    target_ra = cmd[3:]

                    print("RA set:", target_ra)

                    conn.sendall(b"1")

                # Set DEC
                elif cmd.startswith(":Sd"):

                    target_dec = cmd[3:]

                    print("DEC set:", target_dec)

                    conn.sendall(b"1")

                # Slew
                elif cmd == ":MS":

                    print("SLEW command received")

                    slew()

                    conn.sendall(b"0")

                # Abort slew
                elif cmd.startswith(":Q"):

                    alpaca_put(
                        f"/api/v1/telescope/{DEVICE}/abortslew",
                        {}
                    )

                    conn.sendall(b"1")

                else:

                    conn.sendall(b"1")

    except Exception as e:

        print("CLIENT ERROR:", e)

    finally:

        conn.close()

        print("Client disconnected")
