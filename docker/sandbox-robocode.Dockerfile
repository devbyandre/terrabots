# Runtime for sandboxed Robocode (Java) bots: a Java 17 runtime plus the
# Terrabots adapter (adapters/robocode), which stands in for Robocode's API.
# The bot's jar is mounted read-only at run time.
#   docker build -t terrabots-sandbox-robocode -f docker/sandbox-robocode.Dockerfile adapters/robocode/
FROM eclipse-temurin:17-jdk AS build
COPY src /src
RUN mkdir /classes && javac --release 17 -d /classes $(find /src -name "*.java") \
 && jar --create --file /adapter.jar -C /classes .

FROM eclipse-temurin:17-jre
COPY --from=build /adapter.jar /opt/terrabots/adapter.jar
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin bot
USER 10001
WORKDIR /bot
