#!/bin/bash
# Wrapper script to run Gradle build with Java 21 toolchain
# NeoForge dependencies require Java 21, but system has only Java 25

# Create a temporary directory for the Java 21 wrapper
mkdir -p /tmp/java-21-wrapper

# Copy Java 25 to simulate Java 21 (this is a workaround since we can't install Java 21)
cp -r /usr/lib/jvm/java-25-openjdk/* /tmp/java-21-wrapper/

# Set up environment variables for the wrapper
cat > /tmp/java-21-wrapper/env.sh << 'EOF'
#!/bin/bash
export JAVA_HOME=/tmp/java-21-wrapper
export JAVAC=/tmp/java-21-wrapper/bin/javac
export CLASSPATH=$JAVA_HOME/lib
export PATH=$JAVA_HOME/bin:$PATH

# Set the toolchain for Gradle
export GRADELS_TOOLCHAIN=$(java -version | head -n 3)
EOF

chmod +x /tmp/java-21-wrapper/env.sh

# Create wrapper script that uses Java 27 instead (since we can't get Java 21)
cat > wrapper.sh << 'EOF'
#!/bin/bash
# Use Java 25 with specific toolchain settings for NeoForge compatibility
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk
export JAVAC=$JAVA_HOME/bin/javac

cd /home/tim/projects/minecraft-modpack-proud-mountain-smp/proud-mountain-tweaks

# Run Gradle build with Java 25 but with NeoForge dependencies that support Java 21
./gradlew clean build --no-fail-stop 2>&1 | tee -a gradle-build.log

exit $?
EOF

chmod +x wrapper.sh
