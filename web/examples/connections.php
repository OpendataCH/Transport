<?php

$from = isset($_GET['from']) ? $_GET['from'] : false;
$to = isset($_GET['to']) ? $_GET['to'] : false;

$url = 'http://transport.opendata.ch/v1/connections?' . http_build_query(array('from' => $from, 'to' => $to));
$response = json_decode(file_get_contents($url));

?>
<!doctype html>
<html>
<head>
    <meta charset="utf-8">

    <title>Connections Example - Transport API</title>

    <!--[if lt IE 9]><script src="http://html5shim.googlecode.com/svn/trunk/html5.js"></script><![endif]-->

    <meta name="viewport" content="width=device-width, initial-scale=1" />

    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap.min.css" />
    <link rel="stylesheet" href="../media/css/layout.css" />

    <link rel="stylesheet" href="http://ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/themes/base/jquery-ui.css" />

    <script src="http://ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js"></script>
    <script src="http://ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/jquery-ui.min.js"></script>
    <script src="../media/js/moment.min.js"></script>
    <style>
        table {
            width: 100%;
        }

        form.connections-search {
            margin-top: 20px;
        }
    </style>
</head>

<body>

<div class="wrapper">
    <header>
        <h1><a href="../">Transport</a></h1>
        <p>Swiss public transport API</p>
    </header>

    <article>
        <form class="connections-search" method="get" action="">
            <div class="row">
                <div class="span3 station">
                    <label for="from">From:</label>
                    <input type="text" class="span3" id="from" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" autofocus />
                </div>
                <div class="span3 station">
                    <label for="to">To:</label>
                    <input type="text" class="span3" id="to" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" />
                </div>
                <div class="span1">
                    <label>&nbsp;</label>
                    <input type="submit" value="Search" class="btn" />
                </div>
            </div>
        </form>

        <table class="table table-striped">
            <colgroup>
                <col width="120">
                <col width="120">
                <col width="120">
                <col width="140">
            </colgroup>
            <thead>
                <tr>
                    <th align="left">Departure</th>
                    <th align="left">Arrival</th>
                    <th align="left">Duration</th>
                    <th align="left">Travel with</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($response->connections as $connection): ?>
                <tr>
                    <td><?php echo date('H:i', strtotime($connection->from->departure)); ?></td>
                    <td><?php echo date('H:i', strtotime($connection->to->arrival)); ?></td>
                    <td><?php echo htmlentities(substr($connection->duration, 3, 5)); ?></td>
                    <td><?php echo htmlentities(implode(', ', $connection->products)); ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </article>
</div>

</body>
</html>
