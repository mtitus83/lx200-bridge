import socket
import requests

HOST = "0.0.0.0"
PORT = 10001

ALPACA = "http://127.0.0.1:5555"
DEVICE = 1

CLIENT_ID = 1
TX = 1

target_ra = None
target_dec = None


# -----------------------------
# Alpaca helpers
# -----------------------------

def alpaca_get(endpoint):
    global TX
    TX += 1

    r = requests.get(
        f"{ALPACA}{endpoint}",
        params={
            "ClientID": CLIENT_ID,
            "ClientTransactionID": TX
        },
        timeout=5
    )

    return r.json()["Value"]


def alpaca_put(endpoint, data):
    global TX
    TX += 1

    payload = data | {
        "ClientID": CLIENT_ID,
        "ClientTransactionID": TX
    }

    r = requests.put(
        f"{ALPACA}{endpoint}",
        data=payload,
        timeout=5
    )

    print("ALPACA:", r.text)


# -----------------------------
# Coordinate conversion
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
    h = int(hours)
    m = int((hours - h) * 60)
    s = int(((hours - h) * 60 - m) * 60)
    return f"{h:02}:{m:02}:{s:02}#"


def deg_to_dec(deg):
    sign = "+" if deg >= 0 else "-"
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = int(((deg - d) * 60 - m) * 60)
    return f"{sign}{d:02}*{m:02}:{s:02}#"


# -----------------------------
# Slew telescope
# -----------------------------

def slew_seestar(ra, dec):

    try:

        ra_hours = ra_to_hours(ra)
        dec_deg = dec_to_deg(dec)

        print("SLEW:", ra_hours, dec_deg)

        alpaca_put(
            f"/api/v1/telescope/{DEVICE}/slewtocoordinates",
            {
                "RightAscension": ra_hours,
                "Declination": dec_deg
            }
        )

    except Exception as e:

        print("Slew failed:", e)


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

    while True:

        data = conn.recv(1024)

        if not data:
            break

        print("RAW:", data)

        # LX200 ACK probe
        if b"\x06" in data:
            conn.sendall(b"A")
            continue

        # Stellarium alignment probe
        if data.startswith(b"Ka"):
            conn.sendall(b"1")
            continue

        buffer += data

        while b"#" in buffer:

            cmd, buffer = buffer.split(b"#", 1)

            cmd = cmd.decode(errors="ignore")
            cmd = cmd.replace("\n","").replace("\r","").strip()
            cmd = cmd.lstrip("#")

            if not cmd:
                continue

            print("LX200:", cmd)

            # -----------------------------
            # Get RA
            # -----------------------------

            if cmd == ":GR":

                ra = alpaca_get(
                    f"/api/v1/telescope/{DEVICE}/rightascension"
                )

                conn.sendall(hours_to_ra(ra).encode())

            # -----------------------------
            # Get DEC
            # -----------------------------

            elif cmd == ":GD":

                dec = alpaca_get(
                    f"/api/v1/telescope/{DEVICE}/declination"
                )

                conn.sendall(deg_to_dec(dec).encode())

            # -----------------------------
            # Distance query
            # -----------------------------

            elif cmd == ":D":

                conn.sendall(b"0#")

            # -----------------------------
            # Sync command
            # -----------------------------

            elif cmd == ":CM":

                conn.sendall(b"1#")

            # -----------------------------
            # Stellarium capability queries
            # -----------------------------

            elif cmd == ":GG":
                conn.sendall(b"00#")

            elif cmd == ":GW":
                conn.sendall(b"0#")

            elif cmd == ":GVD":
                conn.sendall(b"1.0#")

            elif cmd == ":GVT":
                conn.sendall(b"Seestar#")

            # -----------------------------
            # Time
            # -----------------------------

            elif cmd == ":GL":

                conn.sendall(b"12:00:00#")

            # -----------------------------
            # Date
            # -----------------------------

            elif cmd == ":GC":

                conn.sendall(b"01/01/24#")

            # -----------------------------
            # Product name
            # -----------------------------

            elif cmd == ":GVP":

                conn.sendall(b"SeestarBridge#")

            # -----------------------------
            # Firmware version
            # -----------------------------

            elif cmd == ":GVN":

                conn.sendall(b"1.0#")

            # -----------------------------
            # Longitude
            # -----------------------------

            elif cmd == ":Gg":

                conn.sendall(b"-076*30:00#")

            # -----------------------------
            # Latitude
            # -----------------------------

            elif cmd == ":Gt":

                conn.sendall(b"+38*30:00#")

            # -----------------------------
            # Set RA
            # -----------------------------

            elif cmd.startswith(":Sr"):

                target_ra = cmd[3:]

                print("RA set:", target_ra)

                conn.sendall(b"1")

            # -----------------------------
            # Set DEC
            # -----------------------------

            elif cmd.startswith(":Sd"):

                target_dec = cmd[3:]

                print("DEC set:", target_dec)

                conn.sendall(b"1")

            # -----------------------------
            # Slew command
            # -----------------------------

            elif cmd == ":MS":

                print("SLEW command received")

                if target_ra and target_dec:
                    slew_seestar(target_ra, target_dec)

                conn.sendall(b"0")

            # -----------------------------
            # Abort slew
            # -----------------------------

            elif cmd.startswith(":Q"):

                print("STOP command")

                alpaca_put(
                    f"/api/v1/telescope/{DEVICE}/abortslew",
                    {}
                )

                conn.sendall(b"1")

            else:

                print("UNKNOWN COMMAND:", cmd)

                conn.sendall(b"1")

    conn.close()
