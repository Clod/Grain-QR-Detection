<!-- PROJECT LOGO -->
<br />
<p align="center">
  <h3 align="center">Photo Gallery</h3>

  <p align="center">
    Simple website to updload photos using Streamlit and a ftp server.
  </p>
</p>



<!-- ABOUT THE PROJECT -->
## Built With

* [streamlit](https://streamlit.io/)



<!-- GETTING STARTED -->
## Getting Started

This guide will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

The application requires a running FTP server to store the uploaded images. You can run one locally using Docker.

*   **FTP Server (using Docker)**

    Run the following command to start a `pure-ftpd` server in a Docker container. This command sets up a user with the default credentials used by the application (`myuser`/`mypassword`).

    ```sh
    docker run -d --name ftpd_server -p 21:21 -p 30000-30009:30000-30009 -e "PUBLICHOST=localhost" -e "FTP_USER_NAME=myuser" -e "FTP_USER_PASS=mypassword" -e "FTP_USER_HOME=/home/myuser" -e TLS=2 -v ftpdata:/home/myuser stilliard/pure-ftpd:hardened
    ```

### Local Installation

1.  **Clone the repo**
    ```sh
    git clone https://github.com/lucasliano/photo-Gallery-streamlit.git
    cd photo-Gallery-streamlit
    ```
2.  **Create and activate a virtual environment**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3.  **Install dependencies**
    ```sh
    pip install -r requirements.txt
    ```
4.  **Run the Streamlit app**
    ```sh
    streamlit run app.py
    ```

## Running with Docker

Build the Docker image with:

```sh
docker build -t camerastreamlitftp .
```

And run with:

```sh
docker run -p 8501:8501 -e FTP_HOST="host.docker.internal" -e FTP_USER="myuser" -e FTP_PASS="mypassword" camerastreamlitftp
```


<!-- LICENSE -->
## License
Distributed under the MIT License. See `LICENSE` for more information.


<!-- CONTACT -->
## Contact

Claudio Grasso - claudio.grasso@yahoo.com
Lucas Liaño - lliano@frba.utn.edu.ar

Project Link: [https://github.com/lucasliano/photo-Gallery-streamlit](https://github.com/lucasliano/photo-Gallery-streamlit)


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->