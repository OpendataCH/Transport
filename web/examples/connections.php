<?php

$from = isset($_GET['from']) ? $_GET['from'] : false;
$to = isset($_GET['to']) ? $_GET['to'] : false;
$search = $from && $to;

if ($search) {
    $url = 'http://transport.opendata.ch/v1/connections?' . http_build_query(array('from' => $from, 'to' => $to));
    $response = json_decode(file_get_contents($url));

    if ($response->from) {
        $from = $response->from->name;
    }
    if ($response->to) {
        $to = $response->to->name;
    }
}

?>
<!doctype html>
<html>
<head>
    <meta charset="utf-8">

    <title>Connections Example - Transport API</title>

    <!--[if lt IE 9]><script src="http://html5shim.googlecode.com/svn/trunk/html5.js"></script><![endif]-->

    <meta name="viewport" content="width=device-width, initial-scale=1" />

    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap.min.css" />
    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap-responsive.min.css" />
    <link rel="stylesheet" href="../media/css/layout.css" />

    <link rel="stylesheet" href="http://ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/themes/base/jquery-ui.css" />

    <script src="http://ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js"></script>
    <script src="http://ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/jquery-ui.min.js"></script>
    <script src="../media/js/moment.min.js"></script>
    <style>
        h1 {
            font-size: 5em;
        }

        .station input {
            width: 92%;
        }

        .sections td {
            padding: 4px 8px;
        }

        .table tbody tr:hover td {
            background-color: inherit;
        }
        
        .table th {
            font-weight: normal;
        }
    </style>
    <script>
        $(function () {
            if (!('ontouchstart' in window)) {

                $('table.connections > tbody > tr:nth-child(even)').hide();

                $('table.connections > tbody > tr:nth-child(odd)').each(function () {
                    $(this).css('cursor', 'pointer').click(function () {
                        $(this).next().toggle();
                    });
                });
            }
        });
    </script>
</head>

<body>

<div class="container">
    <div class="page-header">
        <h1><a href="../">Transport</a> <small>Swiss public transport API</small></h1>
    </div>

    <div class="row-fluid">
        <div class="span5">
        
        <form method="get" action="">
            <div class="row-fluid">
                <div class="span4 station">
                    <label for="from">From:</label>
                    <input type="text" id="from" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" autofocus />
                </div>
                <div class="span4 station">
                    <label for="to">To:</label>
                    <input type="text" id="to" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" />
                </div>
                <div class="span1">
                    <label>&nbsp;</label>
                    <input type="submit" value="Search" class="btn" />
                </div>
            </div>
        </form>
        
        </div>
        <div class="span7">

        <?php if ($search): ?>
        <table class="table connections">
            <colgroup>
                <col width="27%">
                <col width="27%">
                <col width="27%">
                <col width="19%">
            </colgroup>
            <thead>
                <tr>
                    <th>Departure</th>
                    <th>Arrival</th>
                    <th>Duration</th>
                    <th>
                        <span class="visible-phone">Pl.</span>
                        <span class="hidden-phone">Platform</span>
                    </th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($response->connections as $connection): ?>
                    <tr style="background-color: #F9F9F9">
                        <td><?php echo date('H:i', strtotime($connection->from->departure)); ?></td>
                        <td><?php echo date('H:i', strtotime($connection->to->arrival)); ?></td>
                        <td><?php echo htmlentities(substr($connection->duration, 3, 5)); ?></td>
                        <td><?php echo htmlentities($connection->from->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                    </tr>
                    <tr>
                        <td colspan="5" style="padding: 0; border-top: 0;">
                            <table class="table sections">
                                <colgroup>
                                    <col width="27%">
                                    <col width="54%">
                                    <col width="19%">
                                </colgroup>
                                <tbody>
                                    <?php foreach ($connection->sections as $section): ?>
                                        <tr>
                                            <td rowspan="2"><?php echo date('H:i', strtotime($section->departure->departure)); ?></td>
                                            <td>
                                                <?php echo htmlentities($section->departure->station->name, ENT_QUOTES, 'UTF-8'); ?>
                                            </td>
                                            <td><?php echo htmlentities($section->departure->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                                        </tr>
                                        <tr>
                                            <td style="border-top: 0;">
                                                <span class="muted">
                                                <?php if ($section->journey): ?>
                                                    <?php echo htmlentities($section->journey->category, ENT_QUOTES, 'UTF-8'); ?>
                                                    <?php echo htmlentities($section->journey->number, ENT_QUOTES, 'UTF-8'); ?>
                                                <?php else: ?>
                                                    Walk
                                                <?php endif; ?>
                                                </span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="border-top: 0;"><?php echo date('H:i', strtotime($section->arrival->arrival)); ?></td>
                                            <td style="border-top: 0;">
                                                <?php echo htmlentities($section->arrival->station->name, ENT_QUOTES, 'UTF-8'); ?>
                                            </td>
                                            <td style="border-top: 0;"><?php echo htmlentities($section->arrival->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                                        </tr>
                                    <?php endforeach; ?>
                                </tbody>
                            </table>
                        </td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        <?php endif; ?>
        
    </div>
</div>

</body>
</html>
