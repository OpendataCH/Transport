<?php

$from = isset($_GET['from']) ? $_GET['from'] : false;
$to = isset($_GET['to']) ? $_GET['to'] : false;
$via = isset($_GET['via']) ? $_GET['via'] : false;
$datetime = isset($_GET['datetime']) ? $_GET['datetime'] : '';
$page = isset($_GET['page']) ? ((int) $_GET['page']) - 1 : 0;
$c = isset($_GET['c']) ? (int) $_GET['c'] : false;

$stationsFrom = array();
$stationsTo = array();

$search = $from && $to;
if ($search) {

    $query = array(
        'from' => $from,
        'to' => $to,
        'page' => $page,
        'limit' => 6,
    );

    if ($datetime) {
        $query['date'] = date('Y-m-d', strtotime($datetime));
        $query['time'] = date('H:i', strtotime($datetime));
    }
    
    if ($via) {
        $query['via'] = $via;
    }

    $url = 'http://transport.opendata.ch/v1/connections?' . http_build_query($query);
    $response = json_decode(file_get_contents($url));

    if ($response->from) {
        $from = $response->from->name;
    }
    if ($response->to) {
        $to = $response->to->name;
    }

    if (isset($response->stations->from[0])) {
        if ($response->stations->from[0]->score < 101) {
            foreach (array_slice($response->stations->from, 1, 3) as $station) {
                if ($station->score > 97) {
                    $stationsFrom[] = $station->name;
                }
            }
        }
    }

    if (isset($response->stations->to[0])) {
        if ($response->stations->to[0]->score < 101) {
            foreach (array_slice($response->stations->to, 1, 3) as $station) {
                if ($station->score > 97) {
                    $stationsTo[] = $station->name;
                }
            }
        }
    }
}

?>
<!doctype html>
<html>
<head>
    <meta charset="utf-8">

    <title>
        <?php if ($search): ?>
            <?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?> – <?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>
        <?php else: ?>
            Transport
        <?php endif; ?>
    </title>

    <!--[if lt IE 9]><script src="//html5shim.googlecode.com/svn/trunk/html5.js"></script><![endif]-->

    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />

    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap.min.css" />
    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap-responsive.min.css" />
    <link rel="stylesheet" href="../media/css/layout.css" />

    <link rel="stylesheet" href="//ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/themes/base/jquery-ui.css" />

    <script src="//ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js"></script>
    <script src="../media/js/moment.min.js"></script>
    <style>
        h1 {
            font-size: 5em;
        }

        .station input {
            width: 92%;
        }
        
        .later {
            text-align: right;
        }

        .row-fluid + .row-fluid {
            padding-top: 3px;
        }

        .date,
        .apply {
            padding-top: 5px;
        }

        .date input {
            width: 92%;
        }
        
        .apply input {
            float: left;
        }

        .apply a {
            display: block;
            float: left;
            padding: 6px 10px;
        }

        input.submit {
            position: absolute;
            top: 0;
            left: 0;
            z-index: 0;
            width: 1px;
            height: 1px;
            visibility: hidden;
        }

        .table tbody + tbody {
            border-top: 0;
        }

        .table tbody tr:hover td {
            background-color: inherit;
        }

        .table th {
            font-weight: normal;
        }

        .table tr.connection {
            cursor: pointer;
        }

        .table tr.section {
            background-color: #f5f5f5;
            cursor: default;
        }

        .pager {
            display: none;
        }
        
        @media (max-width: 767px) {
            body {
                padding-top: 20px;
                padding-bottom: 30px;
            }

            form {
                margin-bottom: 8px;
            }
            
            .date input {
                height: 26px;
                padding: 0;
                border-color: #bbb;
            }
            
            .date input:focus {
                border-color: #1a81d2;
            }

            .row-fluid .fluid {
                float: left;
                margin-left: 12px;
                width: 48%;
            }
        }
    </style>
    <script>
        $(function () {

            if (navigator.geolocation) {

                if (!$('input[name=from]').val()) {

                    $('input[name=from]').attr('placeholder', 'Locating...');

                    var i = 0;
                    var interval = setInterval(function () {
                        i = (i + 1) % 4;
                        var message = 'Locating';
                        for (var j = 0; j < i; j++) {
                            message += '.';
                        }
                        $('input[name=from]').attr('placeholder', message);
                    }, 400);

                    // get location for from
                    var watch = navigator.geolocation.watchPosition(function (position) {

                        if (position.coords.accuracy < 100) {

                            // stop locating
                            navigator.geolocation.clearWatch(watch);

                            var lat = position.coords.latitude;
                            var lng = position.coords.longitude;

                            $.get('../v1/locations', {x: lat, y: lng}, function(data) {

                                clearInterval(interval);
                                $('input[name=from]').attr('placeholder', 'From');

                                $(data.stations).each(function (i, station) {

                                    if (!$('input[name=from]').val()) {
                                        $('input[name=from]').val(station.name);
                                    }

                                    return false;
                                });
                            });
                        }
    
                    }, function(error) {
                        // ignore
                    }, {
                        enableHighAccuracy:true,
                        maximumAge: 10000,
                        timeout: 30000
                    });
                }
            }

            function reset() {
                $('table.connections tr.connection').show();
                $('table.connections tr.section').hide();
            }

            $('table.connections tr.connection').bind('click', function (e) {

                reset();

                var $this = $(this);
                $this.hide();
                $this.nextAll('tr.section').show();

                if ('replaceState' in window.history) {
                    history.replaceState({}, '', '?' + $('.pager').serialize() + '&c=' + $this.data('c'));
                }
            });

            $('.station input').bind('focus', function () {
                var that = this;
                setTimeout(function () {
                    that.setSelectionRange(0, 9999);
                }, 10);
            });
        });
    </script>
</head>

<body>

<div class="container">
    <div class="page-header hidden-phone">
        <h1><a href="../">Transport</a> <small>Swiss public transport API</small></h1>
    </div>

    <div class="row-fluid">
        <div class="span5">

        <form method="get" action="">
            <div class="row-fluid">
                <div class="span5 fluid station">
                    <input type="text" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" placeholder="From" autocapitalize="on" />
                    <?php $i = count($stationsFrom); if ($i > 0): ?>
                        <p>
                            Did you mean:
                            <?php foreach ($stationsFrom as $station): ?>
                                <a href="connections.php?<?php echo htmlentities(http_build_query(array('from' => $station, 'to' => $to, 'datetime' => $datetime)), ENT_QUOTES, 'UTF-8'); ?>"><?php echo htmlentities($station, ENT_QUOTES, 'UTF-8'); ?></a><?php if ($i-- > 1): ?>, <?php endif; ?>
                            <?php endforeach ?>
                        </p>
                    <?php endif; ?>
                </div>
                <div class="span5 fluid station">
                    <input type="text" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" placeholder="To" autocapitalize="on" autofocus />
                    <?php $i = count($stationsFrom); if ($i > 0): ?>
                        <p>
                            Did you mean:
                            <?php foreach ($stationsTo as $station): ?>
                                <a href="connections.php?<?php echo htmlentities(http_build_query(array('from' => $from, 'to' => $station, 'datetime' => $datetime)), ENT_QUOTES, 'UTF-8'); ?>"><?php echo htmlentities($station, ENT_QUOTES, 'UTF-8'); ?></a><?php if ($i-- > 1): ?>, <?php endif; ?>
                            <?php endforeach ?>
                        </p>
                    <?php endif; ?>
                </div>
            </div>
            <div class="row-fluid">
                <div class="span5 fluid date">
                    <input type="datetime-local" name="datetime" value="<?php echo htmlentities($datetime, ENT_QUOTES, 'UTF-8'); ?>" placeholder="Date and time" step="300" />
                </div>
                <div class="span5 fluid apply">
                    <input type="submit" class="btn" value="Search" />
                    <a href="connections.php">Clear</a>
                </div>
            </div>
        </form>
        
        </div>
        <div class="span7">

        <?php if ($search): ?>
        <table class="table connections">
            <colgroup>
                <col width="20%">
                <col width="57%">
                <col width="23%">
            </colgroup>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Journey</th>
                    <th>
                        <span class="visible-phone">Pl.</span>
                        <span class="hidden-phone">Platform</span>
                    </th>
                </tr>
            </thead>
            <?php $j = 0; ?>
            <?php foreach ($response->connections as $connection): ?>
                <?php $j++; ?>
                <tbody>
                    <tr class="connection"<?php if ($j == $c): ?> style="display: none;"<?php endif; ?> data-c="<?php echo $j; ?>">
                        <td>
                            <?php echo date('H:i', strtotime($connection->from->departure)); ?>
                            <?php if ($connection->from->delay): ?>
                                <span style="color: #a20d0d;"><?php echo '+' . $connection->from->delay; ?></span>
                            <?php endif; ?>
                            <br/>
                            <?php echo date('H:i', strtotime($connection->to->arrival)); ?>
                            <?php if ($connection->to->delay): ?>
                                <span style="color: #a20d0d;"><?php echo '+' . $connection->to->delay; ?></span>
                            <?php endif; ?>
                        </td>
                        <td>
                            <?php echo htmlentities(substr($connection->duration, 4, 4)); ?>′<br/>
                            <span class="muted">
                            <?php echo htmlentities(implode(', ', $connection->products)); ?>
                            </span>
                        </td>
                        <td>
                            <?php if ($connection->from->prognosis->platform): ?>
                                <span style="color: #a20d0d;"><?php echo htmlentities($connection->from->prognosis->platform, ENT_QUOTES, 'UTF-8'); ?></span>
                            <?php else: ?>
                                <?php echo htmlentities($connection->from->platform, ENT_QUOTES, 'UTF-8'); ?>
                            <?php endif; ?>
                            <br/>
                            <?php if ($connection->capacity2nd > 0): ?>
                                <span class="muted">
                                    <?php for ($i = 0; $i < 3; $i++) { echo $i < $connection->capacity2nd ? '●' : '○'; } ?>
                                </span>
                            <?php endif; ?>
                        </td>
                    </tr>
                    <?php $i = 0; foreach ($connection->sections as $section): ?>
                        <tr class="section"<?php if ($j != $c): ?> style="display: none;"<?php endif; ?>>
                            <td rowspan="2">
                                <?php echo date('H:i', strtotime($section->departure->departure)); ?>
                                <?php if ($section->departure->delay): ?>
                                    <span style="color: #a20d0d;"><?php echo '+' . $section->departure->delay; ?></span>
                                <?php endif; ?>
                            </td>
                            <td>
                                <?php echo htmlentities($section->departure->station->name, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                            <td>
                                <?php if ($section->departure->prognosis->platform): ?>
                                    <span style="color: #a20d0d;"><?php echo htmlentities($section->departure->prognosis->platform, ENT_QUOTES, 'UTF-8'); ?></span>
                                <?php else: ?>
                                    <?php echo htmlentities($section->departure->platform, ENT_QUOTES, 'UTF-8'); ?>
                                <?php endif; ?>
                            </td>
                        </tr>
                        <tr class="section"<?php if ($j != $c): ?> style="display: none;"<?php endif; ?>>
                            <td style="border-top: 0; padding: 4px 8px;">
                                <span class="muted">
                                <?php if ($section->journey): ?>
                                    <?php echo htmlentities($section->journey->name, ENT_QUOTES, 'UTF-8'); ?>
                                <?php else: ?>
                                    Walk
                                <?php endif; ?>
                                </span>
                            </td>
                            <td style="border-top: 0; padding: 4px 8px;">
                                <span class="muted">
                                    <?php if ($section->journey && $section->journey->capacity2nd > 0): ?>
                                        <?php for ($i = 0; $i < 3; $i++) { echo $i < $section->journey->capacity2nd ? '●' : '○'; } ?>
                                    <?php endif; ?>
                                </span>
                            </td>
                        </tr>
                        <tr class="section"<?php if ($j != $c): ?> style="display: none;"<?php endif; ?>>
                            <td style="border-top: 0;">
                                <?php echo date('H:i', strtotime($section->arrival->arrival)); ?>
                                <?php if ($section->arrival->delay): ?>
                                    <span style="color: #a20d0d;"><?php echo '+' . $section->arrival->delay; ?></span>
                                <?php endif; ?>
                            </td>
                            <td style="border-top: 0;">
                                <?php echo htmlentities($section->arrival->station->name, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                            <td style="border-top: 0;">
                                <?php if ($section->arrival->prognosis->platform): ?>
                                    <span style="color: #a20d0d;"><?php echo htmlentities($section->arrival->prognosis->platform, ENT_QUOTES, 'UTF-8'); ?></span>
                                <?php else: ?>
                                    <?php echo htmlentities($section->arrival->platform, ENT_QUOTES, 'UTF-8'); ?>
                                <?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            <?php endforeach; ?>
        </table>

        <?php $datetime = $datetime ?: date('Y-m-d H:i:s'); ?>
        <form class="pager">
            <input type="hidden" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" />
            <input type="hidden" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" />
            <input type="hidden" name="datetime" value="<?php echo htmlentities($datetime, ENT_QUOTES, 'UTF-8'); ?>" />
            <input type="hidden" name="page" value="<?php echo htmlentities($page + 1, ENT_QUOTES, 'UTF-8'); ?>" />
        </form>
        <div class="row-fluid">
            <div class="span6 fluid">
                <a href="connections.php?<?php echo htmlentities(http_build_query(array('from' => $from, 'to' => $to, 'datetime' => $datetime, 'page' => $page)), ENT_QUOTES, 'UTF-8'); ?>">Earlier connections</a>
            </div>
            <div class="span6 fluid later">
                <a href="connections.php?<?php echo htmlentities(http_build_query(array('from' => $from, 'to' => $to, 'datetime' => $datetime, 'page' => $page + 2)), ENT_QUOTES, 'UTF-8'); ?>">Later connections</a>
            </div>
        </div>
        <?php endif; ?>
    </div>
</div>

</body>
</html>
