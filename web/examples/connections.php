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

    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />

    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap.min.css" />
    <link rel="stylesheet" href="../media/bootstrap/css/bootstrap-responsive.min.css" />
    <link rel="stylesheet" href="../media/css/layout.css" />

    <link rel="stylesheet" href="http://ajax.googleapis.com/ajax/libs/jqueryui/1.8.16/themes/base/jquery-ui.css" />

    <script src="http://ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js"></script>
    <script src="../media/js/moment.min.js"></script>
    <style>
        h1 {
            font-size: 5em;
        }

        .station input {
            width: 92%;
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

        .table tbody {
            cursor: pointer;
        }

        .table tr.section {
            background-color: #F9F9F9;
        }
        
        @media (max-width: 480px) {
            body {
                padding-top: 18px;
            }
        }
    </style>
    <script>
        $(function () {

            function reset() {
                $('table.connections tr.connection').show();
                $('table.connections tr.section').hide();
            }

            reset();

            // faster touch response
            var touch = {target: false, moved: false, down: false};
            $(document.body).bind('touchstart', function(e) {
                touch.target = $(e.originalEvent.touches[0].target);
                touch.down = true;
            });
            $(document.body).bind('touchmove', function(e) {
                touch.moved = true;
            });
            $(document.body).bind('touchend', function(e) {
                if (!touch.moved) {
                    e.preventDefault();
                    touch.target.trigger('click');
                }
                touch.moved = false;
                touch.down = false;
            });

            $('table.connections tbody').bind('click', function (e) {

                reset();

                $this = $(this);
                if ($this.data('open')) {

                    $this.data('open', false);

                } else {

                    $('tr.connection', this).hide();
                    $('tr.section', this).show();
                    $this.data('open', true);
                }
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
                <div class="span5 station">
                    <label for="from">From:</label>
                    <input type="text" id="from" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" autofocus />
                </div>
                <div class="span5 station">
                    <label for="to">To:</label>
                    <input type="text" id="to" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" />
                </div>
                <input type="submit" value="S" class="submit" />
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
            <?php foreach ($response->connections as $connection): ?>
                <tbody>
                    <tr class="connection">
                        <td><?php echo date('H:i', strtotime($connection->from->departure)); ?><br/><?php echo date('H:i', strtotime($connection->to->arrival)); ?></td>
                        <td>
                            <?php echo htmlentities(substr($connection->duration, 4, 4)); ?>′<br/>
                            <?php echo htmlentities(implode(', ', $connection->products)); ?>
                        </td>
                        <td><?php echo htmlentities($connection->from->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                    </tr>
                    <?php $i = 0; foreach ($connection->sections as $section): ?>
                        <tr class="section">
                            <td rowspan="2"><?php echo date('H:i', strtotime($section->departure->departure)); ?></td>
                            <td>
                                <?php echo htmlentities($section->departure->station->name, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                            <td><?php echo htmlentities($section->departure->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                        </tr>
                        <tr class="section">
                            <td style="border-top: 0; padding: 4px 8px;" colspan="2">
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
                        <tr class="section">
                            <td style="border-top: 0;"><?php echo date('H:i', strtotime($section->arrival->arrival)); ?></td>
                            <td style="border-top: 0;">
                                <?php echo htmlentities($section->arrival->station->name, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                            <td style="border-top: 0;"><?php echo htmlentities($section->arrival->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            <?php endforeach; ?>
        </table>
        <?php endif; ?>
        
    </div>
</div>

</body>
</html>
