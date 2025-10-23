"""
Network Listener Module
Handles TCP socket binding and accepting client connections
"""

import socket
import ssl
import threading
from common.config import HOST, PORT, TLS_ENABLED, SERVER_CERT, SERVER_KEY
from server.client_handler import handle_client
from server.logger_config import logger


def start_listener():
    """
    Start TCP listener on configured HOST:PORT
    Accepts incoming client connections and spawns handler threads
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)

        # Wrap socket with TLS if enabled
        if TLS_ENABLED:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(SERVER_CERT, SERVER_KEY)
            # Don't require client certificates (we use token auth instead)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            logger.info("TLS/SSL encryption enabled")

        # Get and display server IP
        local_ip = socket.gethostbyname(socket.gethostname())
        logger.info(f"Server started on {local_ip}:{PORT}")
        logger.info(f"Listening on all interfaces ({HOST}:{PORT})")
        logger.info("Waiting for client connections...")

        while True:
            client_socket, client_address = server_socket.accept()

            # Wrap with TLS if enabled
            if TLS_ENABLED:
                try:
                    client_socket = ssl_context.wrap_socket(client_socket, server_side=True)
                    logger.debug(f"TLS handshake completed with {client_address[0]}")
                except ssl.SSLError as e:
                    logger.warning(f"TLS handshake failed with {client_address[0]}: {e}")
                    client_socket.close()
                    continue

            # Spawn new thread for each client
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()

    except KeyboardInterrupt:
        logger.info("Listener shutting down...")
    except Exception as e:
        logger.error(f"Listener error: {e}")
    finally:
        server_socket.close()
