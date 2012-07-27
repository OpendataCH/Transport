<?php

$from = isset($_GET['from']) ? $_GET['from'] : false;
$to = isset($_GET['to']) ? $_GET['to'] : false;
$datetime = isset($_GET['datetime']) ? $_GET['datetime'] : '';
$page = isset($_GET['page']) ? ((int) $_GET['page']) - 1 : 0;

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

    $url = 'http://transport.opendata.ch/v1/connections?' . http_build_query($query);
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
        
        .later {
            text-align: right;
        }

        .row-fluid + .row-fluid {
            padding-top: 3px;
        }

        .date {
            padding-top: 5px;
        }

        .date input {
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
        
        @media (max-width: 767px) {
            body {
                padding-top: 20px;
                padding-bottom: 30px;
            }
            
            form {
                margin-bottom: 8px;
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

            function reset() {
                $('table.connections tr.connection').show();
                $('table.connections tr.section').hide();
            }

            $('table.connections tbody').bind('click', function (e) {

                var $this = $(this);

                reset();

                if ($this.data('open')) {

                    $this.data('open', false);

                } else {

                    $this.find('tr.connection').hide();
                    $this.find('tr.section').show();
                    $this.data('open', true);
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
                    <input type="text" name="from" value="<?php echo htmlentities($from, ENT_QUOTES, 'UTF-8'); ?>" placeholder="From" autocapitalize="on" autofocus />
                </div>
                <div class="span5 fluid station">
                    <input type="text" name="to" value="<?php echo htmlentities($to, ENT_QUOTES, 'UTF-8'); ?>" placeholder="To" autocapitalize="on" />
                </div>
            </div>
            <div class="row-fluid">
                <div class="span5 fluid date">
                    <input type="datetime-local" name="datetime" value="<?php echo htmlentities($datetime, ENT_QUOTES, 'UTF-8'); ?>" placeholder="Date and time" step="300" />
                </div>
                <div class="span2 fluid apply">
                    <input type="submit" class="btn" value="Search" />
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
            <?php foreach ($response->connections as $connection): ?>
                <tbody>
                    <tr class="connection">
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
                            <?php echo htmlentities($connection->from->platform, ENT_QUOTES, 'UTF-8'); ?><br/>
                            <?php if ($connection->capacity2nd > 0): ?>
                                <span class="muted">
                                    <?php for ($i = 0; $i < 3; $i++) { echo $i < $connection->capacity2nd ? '●' : '○'; } ?>
                                </span>
                            <?php endif; ?>
                        </td>
                    </tr>
                    <?php $i = 0; foreach ($connection->sections as $section): ?>
                        <tr class="section" style="display: none;">
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
                                <?php echo htmlentities($section->departure->platform, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                        </tr>
                        <tr class="section" style="display: none;">
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
                                    <?php if ($section->departure->prognosis->capacity2nd): ?>
                                        <?php for ($i = 0; $i < 3; $i++) { echo $i < $section->departure->prognosis->capacity2nd ? '●' : '○'; } ?>
                                    <?php endif; ?>
                                </span>
                            </td>
                        </tr>
                        <tr class="section" style="display: none;">
                            <td style="border-top: 0;">
                                <?php echo date('H:i', strtotime($section->arrival->arrival)); ?>
                                <?php if ($section->arrival->delay): ?>
                                    <span style="color: #a20d0d;"><?php echo '+' . $section->arrival->delay; ?></span>
                                <?php endif; ?>
                            </td>
                            <td style="border-top: 0;">
                                <?php echo htmlentities($section->arrival->station->name, ENT_QUOTES, 'UTF-8'); ?>
                            </td>
                            <td style="border-top: 0;"><?php echo htmlentities($section->arrival->platform, ENT_QUOTES, 'UTF-8'); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            <?php endforeach; ?>
        </table>

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
