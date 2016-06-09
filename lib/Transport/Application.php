<?php

namespace Transport;

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\Serializer\Encoder\JsonEncoder;
use Symfony\Component\Serializer\Serializer;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\StationBoardQuery;
use Transport\Normalizer\FieldsNormalizer;
use Transport\Web\ConnectionQueryParser;
use Transport\Web\LocationQueryParser;

/**
 * @SWG\Swagger(
 *     schemes={"http", "https"},
 *     host="transport.opendata.ch",
 *     basePath="/v1",
 *     produces={"application/json"},
 *     @SWG\Info(title="Transport API", version="1.0")
 * )
 * @SWG\Tag(
 *   name="locations",
 *   description="Search for stations and locations"
 * )
 * @SWG\Tag(
 *   name="connections",
 *   description="Search for connections"
 * )
 * @SWG\Tag(
 *   name="stationboard",
 *   description="Get station board"
 * )
 */
class Application extends \Silex\Application
{
    public function __construct()
    {
        parent::__construct();

        $app = $this;

        // default config
        $app['debug'] = true;
        $app['http_cache'] = false;
        $app['buzz.client'] = null;
        $app['monolog.level'] = \Monolog\Logger::ERROR;
        $app['redis.config'] = false; // array('host' => 'localhost', 'port' => 6379);
        $app['stats.config'] = ['enabled' => false];
        $app['rate_limiting.config'] = ['enabled' => false, 'limit' => 150];
        $app['proxy'] = false;
        $app['proxy_server.address'] = null;

        /// load config
        $config = __DIR__.'/../../config.php';
        if (stream_resolve_include_path($config)) {
            include $config;
        }

        // New Relic
        $app->register(new \Ekino\Bundle\NewRelicBundle\Silex\EkinoNewRelicServiceProvider(), [
            'new_relic.application_name' => false,
            'new_relic.log_exceptions'   => true,
        ]);

        // HTTP cache
        if ($app['http_cache']) {
            $app->register(new \Silex\Provider\HttpCacheServiceProvider(), [
                'http_cache.cache_dir' => __DIR__.'/../../var/cache/',
                'http_cache.options'   => ['debug' => $app['debug']],
            ]);
        }

        // Exception handler
        $app->error(function (\Exception $e, $code) use ($app) {

            if ($app['debug']) {
                return;
            }

            if ($e instanceof HttpException && $e->getStatusCode() == 429) {
                // don't log rate limiting
            } else {
                $app['stats']->error($e);
            }

            $errors = [['message' => $e->getMessage()]];

            $result = ['errors' => $errors];

            return $app->json($result, $code);
        });

        // Monolog
        $app->register(new \Silex\Provider\MonologServiceProvider(), [
            'monolog.logfile' => __DIR__.'/../../var/logs/transport.log',
            'monolog.level'   => $app['monolog.level'],
            'monolog.name'    => 'transport',
        ]);
        $app->before(function (Request $request) use ($app) {
            $app['monolog']->addInfo('- '.$request->getClientIp().' '.$request->headers->get('referer').' '.$request->server->get('HTTP_USER_AGENT'));
        });

        // if hosted behind a reverse proxy
        if ($app['proxy']) {
            $proxies = [$_SERVER['REMOTE_ADDR']];
            if (is_array($app['proxy'])) {
                $proxies = $app['proxy'];
            }
            Request::setTrustedProxies($proxies);
        }

        // Initialize buzz client
        $client = $app['buzz.client'] ?: new \Buzz\Client\FileGetContents();
        if ($app['proxy_server.address']) {
            $client->setProxy($app['proxy_server.address']);
        }

        // create Transport API
        $app['api'] = new \Transport\API(new \Buzz\Browser($client));

        // allow cross-domain requests, enable cache
        $app->after(function (Request $request, Response $response) {
            $response->headers->set('Access-Control-Allow-Origin', '*');
            if ($app['http_cache']) {
                $response->headers->set('Cache-Control', 's-maxage=30, public');
            }
        });

        // Serializer
        $app['serializer'] = $app->share(function () use ($app) {
            $fields = $app['request']->get('fields') ?: [];

            return new Serializer([new FieldsNormalizer($fields)], ['json' => new JsonEncoder()]);
        });

        // Redis
        $redis = null;
        try {
            if ($app['redis.config']) {
                $redis = new \Predis\Client($app['redis.config']);
                $redis->connect();
            }
        } catch (\Exception $e) {
            $app['monolog']->addError($e->getMessage());
            $redis = null;
        }

        // statistics
        $app['stats'] = new \Transport\Statistics($redis, $app['stats.config']['enabled']);
        $app->after(function (Request $request, Response $response) use ($app) {
            if ($response->getStatusCode() !== 429) {
                $app['stats']->call();
                $app['stats']->resource($request->getPathInfo());
            }
        });

        // rate limiting
        $app['rate_limiting'] = new \Transport\RateLimiting($redis, $app['rate_limiting.config']['enabled'], $app['rate_limiting.config']['limit']);

        $app->before(function (Request $request) use ($app) {

            if ($app['rate_limiting']->isEnabled()) {
                $ip = $request->getClientIp();
                if ($app['rate_limiting']->hasReachedLimit($ip)) {
                    throw new HttpException(429, 'Rate limit of '.$app['rate_limiting']->getLimit().' requests per minute exceeded');
                }
                $app['rate_limiting']->increment($ip);
            }
        });

        $app->after(function (Request $request, Response $response) use ($app) {

            if ($app['rate_limiting']->isEnabled()) {
                $ip = $request->getClientIp();

                $response->headers->set('X-Rate-Limit-Limit', $app['rate_limiting']->getLimit());
                $response->headers->set('X-Rate-Limit-Remaining', $app['rate_limiting']->getRemaining($ip));
                $response->headers->set('X-Rate-Limit-Reset', $app['rate_limiting']->getReset());
            }
        });

        // home
        $app->get('/', function () use ($app) {
            return file_get_contents('index.html');
        })->bind('home');

        // api
        $app->get('/v1/', function () use ($app) {

            return $app->json([
                'date'    => date('c'),
                'author'  => 'Opendata.ch',
                'version' => '1.0',
            ]);
        })->bind('api');

        /**
         * Search locations.
         *
         * Returns the matching locations for the given parameters. Either query or ( x and y ) are required.
         *
         * The locations in the response are scored to determine which is the most exact location.
         *
         * This method can return a refine response, what means that the request has to be redone.
         *
         * @SWG\Get(
         *     path="/locations",
         *     tags={"locations"},
         *     @SWG\Parameter(
         *         name="query",
         *         in="query",
         *         description="Specifies the location name to search for (e.g. Basel)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="x",
         *         in="query",
         *         description="Latitude (e.g. 47.476001)",
         *         type="number"
         *     ),
         *     @SWG\Parameter(
         *         name="y",
         *         in="query",
         *         description="Longitude (e.g. 8.306130)",
         *         type="number"
         *     ),
         *     @SWG\Parameter(
         *         name="type",
         *         in="query",
         *         description="Only with `query` parameter. Specifies the location type, possible types are:<ul><li>`all` (default): Looks up for all types of locations</li><li>`station`: Looks up for stations (train station, bus station)</li><li>`poi`: Looks up for points of interest (Clock tower, China garden)</li><li>`address`: Looks up for an address (Zurich Bahnhofstrasse 33)</li></ul>",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="transportations[]",
         *         in="query",
         *         description="Only with `x` and `y` parameter. Transportation means; one or more of `ice_tgv_rj`, `ec_ic`, `ir`, `re_d`, `ship`, `s_sn_r`, `bus`, `cableway`, `arz_ext`, `tramway_underground` (e.g. transportations[]=ec_ic&transportations[]=bus)",
         *         type="string"
         *     ),
         *     @SWG\Response(
         *         response="200",
         *         description="List of locations",
         *         @SWG\Schema(
         *             type="object",
         *             @SWG\Property(
         *                  property="stations",
         *                  type="array",
         *                  @SWG\Items(ref="#/definitions/Location")
         *             ),
         *         ),
         *     ),
         * )
         */
        $app->get('/v1/locations', function (Request $request) use ($app) {

            $stations = [];

            $x = $request->get('x') ?: null;
            $y = $request->get('y') ?: null;
            $transportations = $request->get('transportations');
            if ($x && $y) {
                $query = new NearbyQuery($x, $y);
                if ($transportations) {
                    $query->transportations = (array) $transportations;
                }
                $stations = $app['api']->findNearbyLocations($query);
            }

            $query = $request->get('query');
            if ($query) {
                $query = new LocationQuery($query, $request->get('type'));
                $stations = $app['api']->findLocations($query);
            }

            $result = ['stations' => $stations];

            $json = $app['serializer']->serialize((object) $result, 'json');

            return new Response($json, 200, ['Content-Type' => 'application/json']);
        })->bind('locations');

        /**
         * Search connections.
         *
         * Returns the next connections from a location to another.
         *
         * @SWG\Get(
         *     path="/connections",
         *     tags={"connections"},
         *     @SWG\Parameter(
         *         name="from",
         *         in="query",
         *         description="Specifies the departure location of the connection (e.g. Lausanne)",
         *         type="string",
         *         required=true
         *     ),
         *     @SWG\Parameter(
         *         name="to",
         *         in="query",
         *         description="Specifies the arrival location of the connection (e.g. Genève)",
         *         type="string",
         *         required=true
         *     ),
         *     @SWG\Parameter(
         *         name="via[]",
         *         in="query",
         *         description="Specifies up to five via locations. When specifying several vias, array notation (via[]=Bern&via[]=Fribourg) is required",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="date",
         *         in="query",
         *         description="Date of the connection, in the format YYYY-MM-DD (e.g. 2012-03-25)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="time",
         *         in="query",
         *         description="Time of the connection, in the format hh:mm (e.g. 17:30)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="isArrivalTime",
         *         in="query",
         *         description="defaults to `0`, if set to `1` the passed `date` and `time` is the arrival time",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="transportations[]",
         *         in="query",
         *         description="Transportation means; one or more of `ice_tgv_rj`, `ec_ic`, `ir`, `re_d`, `ship`, `s_sn_r`, `bus`, `cableway`, `arz_ext`, `tramway_underground` (e.g. transportations[]=ec_ic&transportations[]=bus)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="limit",
         *         in="query",
         *         description="1 - 6. Specifies the number of connections to return. If several connections depart at the same time they are counted as 1.",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="page",
         *         in="query",
         *         description="0 - 10. Allows pagination of connections. Zero-based, so first page is 0, second is 1, third is 2 and so on.",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="direct",
         *         in="query",
         *         description="defaults to `0`, if set to `1` only direct connections are allowed",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="sleeper",
         *         in="query",
         *         description="defaults to `0`, if set to `1` only night trains containing beds are allowed, implies `direct=1`",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="couchette",
         *         in="query",
         *         description="defaults to `0`, if set to `1` only night trains containing couchettes are allowed, implies `direct=1`",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="bike",
         *         in="query",
         *         description="defaults to `0`, if set to `1` only trains allowing the transport of bicycles are allowed",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="accessibility",
         *         in="query",
         *         description="Possible values are `independent_boarding`, `assisted_boarding`, and `advanced_notice`",
         *         type="string"
         *     ),
         *     @SWG\Response(
         *         response="200",
         *         description="A list of connections",
         *         @SWG\Schema(
         *             type="object",
         *             @SWG\Property(
         *                  property="connections",
         *                  type="array",
         *                  @SWG\Items(ref="#/definitions/Connection")
         *             ),
         *         ),
         *     ),
         * )
         */
        $app->get('/v1/connections', function (Request $request) use ($app) {

            $query = LocationQueryParser::create($request);

            // get stations
            $stations = $app['api']->findLocations($query);

            // get connections
            $connections = [];
            $from = reset($stations['from']) ?: null;
            $to = reset($stations['to']) ?: null;
            $via = [];
            foreach ($stations as $k => $v) {
                if (preg_match('/^via[0-9]+$/', $k) && $v) {
                    $via[] = reset($v);
                }
            }

            if ($from && $to) {
                $app['stats']->station($from);
                $app['stats']->station($to);

                $query = ConnectionQueryParser::create($request, $from, $to, $via);

                $errors = ConnectionQueryParser::validate($query);
                if ($errors) {
                    return $app->json(['errors' => $errors], 400);
                }

                $connections = $app['api']->findConnections($query);
            }

            $result = [
                'connections' => $connections,
                'from'        => $from,
                'to'          => $to,
                'stations'    => $stations,
            ];

            $json = $app['serializer']->serialize((object) $result, 'json');

            return new Response($json, 200, ['Content-Type' => 'application/json']);
        })->bind('connections');

        /**
         * Get station board.
         *
         * Returns the next connections leaving from a specific location.
         *
         * @SWG\Get(
         *     path="/stationboard",
         *     tags={"stationboard"},
         *     @SWG\Parameter(
         *         name="station",
         *         in="query",
         *         description="Specifies the location of which a stationboard should be returned (e.g. Aarau)",
         *         type="string",
         *         required=true
         *     ),
         *     @SWG\Parameter(
         *         name="id",
         *         in="query",
         *         description="The id of the station whose stationboard should be returned. Alternative to the station parameter; one of these two is required. If both an id and a station are specified the id has precedence. e.g. 8503059 (for Zurich Stadelhofen)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="limit",
         *         in="query",
         *         description="Number of departing connections to return. This is not a hard limit - if multiple connections leave at the same time it'll return any connections that leave at the same time as the last connection within the limit. For example: `limit=4` will return connections leaving at: 19:30, 19:32, 19:32, 19:35, 19:35. Because one of the connections leaving at 19:35 is within the limit, all connections leaving at 19:35 are shown.",
         *         type="integer"
         *     ),
         *     @SWG\Parameter(
         *         name="transportations[]",
         *         in="query",
         *         description="Transportation means; one or more of `ice_tgv_rj`, `ec_ic`, `ir`, `re_d`, `ship`, `s_sn_r`, `bus`, `cableway`, `arz_ext`, `tramway_underground` (e.g. transportations[]=ec_ic&transportations[]=bus)",
         *         type="string"
         *     ),
         *     @SWG\Parameter(
         *         name="datetime",
         *         in="query",
         *         description="Date and time of departing connections, in the format `YYYY-MM-DD hh:mm` (e.g. 2012-03-25 17:30)",
         *         type="string"
         *     ),
         *     @SWG\Response(
         *         response="200",
         *         description="Stationboard",
         *         @SWG\Schema(
         *             type="object",
         *             @SWG\Property(
         *                  property="station",
         *                  description="The first matched location based on the query. The stationboard will be displayed if this is a station.",
         *                  ref="#/definitions/Station"
         *             ),
         *             @SWG\Property(
         *                  property="stationboard",
         *                  description="A list of journeys with the stop of the line leaving from that station.",
         *                  type="array",
         *                  @SWG\Items(ref="#/definitions/Journey")
         *             ),
         *         ),
         *     ),
         * )
         */
        $app->get('/v1/stationboard', function (Request $request) use ($app) {

            $stationboard = [];

            $limit = $request->get('limit', 40);
            if ($limit > 420) {
                return new Response('Invalid value for Parameter `limit`.', 400);
            }

            $date = $request->get('date');
            if (!$date) {
                $date = $request->get('datetime');
            }
            if ($date) {
                $date = new \DateTime($date, new \DateTimeZone('Europe/Zurich'));
            }

            $transportations = $request->get('transportations');

            $station = $request->get('station') ?: $request->get('id');

            $query = new LocationQuery($station, 'station');
            $stations = $app['api']->findLocations($query);
            $station = reset($stations);

            if ($station instanceof Station) {
                $app['stats']->station($station);

                $query = new StationBoardQuery($station, $date);
                if ($transportations) {
                    $query->transportations = (array) $transportations;
                }
                $query->maxJourneys = $limit;
                $stationboard = $app['api']->getStationBoard($query);
            }

            $result = ['station' => $station, 'stationboard' => $stationboard];

            $json = $app['serializer']->serialize((object) $result, 'json');

            return new Response($json, 200, ['Content-Type' => 'application/json']);
        })->bind('stationboard');

        // Swagger
        $app->get('/swagger.json', function () use ($app) {

            $swagger = \Swagger\scan(__DIR__);

            return new Response($swagger, 200, ['Content-Type' => 'application/json']);

        })->bind('swagger');
    }
}
