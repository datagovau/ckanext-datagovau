TOOLS_IMAGE = 'dga-tools:latest'
TOOLS_ARGS = '--volume /var/run/docker.sock:/var/run/docker.sock --network host --volume /tmp:/tmp'

/*
 * UTC About Midday Sydney time on a Tuesday->Thursday for Prod/Identity,
 * any work hour for Dev/Staging/Pipeline.
 */
CRON_TAB = BRANCH_NAME ==~ /(Production|Identity)/ ? "H H(2-3) * * H(2-4)" : BRANCH_NAME ==~ /(Develop|Staging|Pipeline)/ ? "H H(0-5) * * H(1-5)": ""

pipeline {
    agent none
    triggers {
        pollSCM( '* * * * *')
	    cron( CRON_TAB) 
    }

    options {
        timeout(time: 1, unit: 'HOURS')
        disableConcurrentBuilds()
    }

    stages {
        stage('Build') {
            agent {
                docker {
                    image TOOLS_IMAGE
                    args TOOLS_ARGS
                }
            }

            steps {
                dir('dga-ckan_web') {
                    git branch: 'Develop', credentialsId: 'PAT', url: 'https://github.com/datagovau/dga-ckan_web.git'
                }

                withCredentials([sshUserPrivateKey(credentialsId: "GitHub-ssh", keyFileVariable: 'keyfile')]) {

                    sh '''
                        #!/bin/bash
                        set -e
                        mkdir -p ~/.ssh
                        ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
                        echo "Host github.com" > ~/.ssh/config
                        echo " HostName github.com" >> ~/.ssh/config
                        echo " IdentityFile ${keyfile}" >> ~/.ssh/config

                        git config --global user.email "pipeline@data.gov.au"
                        git config --global user.name "Jenkins"
                   
                        cd ${WORKSPACE}

                        dga-ckan_web/build.sh --clean

                        /home/tools/push.sh
                    '''.stripIndent()
                }
            }
        }

        stage('QA') {
            parallel {
                stage('scan-secrets'){
                    agent {
                        docker {
                            image TOOLS_IMAGE
                            args TOOLS_ARGS
                        }
                    }
                    steps {
                        sh '''\
                        /home/tools/secrets_scan.sh
                        '''.stripIndent()
                    }
                }

                stage('selenium-chrome') {
                    agent {
                        docker {
                            image TOOLS_IMAGE
                            args TOOLS_ARGS
                        }
                    }

                    steps {
                        dir('dga-ckan_web') {
                            git branch: 'Develop', credentialsId: 'PAT', url: 'https://github.com/datagovau/dga-ckan_web.git'
                        }
                        dir('dga-selenium-tests') {
                            git branch: 'Develop', url: 'https://github.com/AusDTO/dga-selenium-tests.git'
                        }
                        sh '''\
                            #!/bin/bash
                            set -ex
                            
                            cp -r dga-selenium-tests/sides/* dga-ckan_web/test/selenium/sides/

                            /home/tools/pull.sh
                            cd dga-ckan_web
                            test/selenium/pull.sh
                            test/selenium/run.sh --browser chrome

                        '''.stripIndent()
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'test/selenium/.logs/*', fingerprint: true
                            junit 'dga-ckan_web/test/selenium/.output/**/*.xml'

                            sh '''
                                rm -rf dga-ckan_web/test/selenium/.logs dga-ckan_web/test/selenium/.output
                            '''.stripIndent()             
                        }
                    }
                }
                stage('selenium-firefox') {
                    agent {
                        docker {
                            image TOOLS_IMAGE
                            args TOOLS_ARGS
                        }
                    }

                    steps {
                        dir('dga-ckan_web') {
                            git branch: 'Develop', credentialsId: 'PAT', url: 'https://github.com/datagovau/dga-ckan_web.git'
                        }
                        dir('dga-selenium-tests') {
                            git branch: 'Develop', url: 'https://github.com/AusDTO/dga-selenium-tests.git'
                        }
                        sh '''\
                            #!/bin/bash
                            set -ex

                            cp -r dga-selenium-tests/sides/* dga-ckan_web/test/selenium/sides/

                            /home/tools/pull.sh

                            dga-ckan_web/test/selenium/pull.sh
                            dga-ckan_web/test/selenium/run.sh --browser firefox

                        '''.stripIndent()
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'dga-ckan_web/test/selenium/.logs/*', fingerprint: true
                            junit 'dga-ckan_web/test/selenium/.output/**/*.xml'

                        }
                    }
                }
                stage('spatial-ingestor') {
                    agent {
                        docker {
                            image TOOLS_IMAGE
                            args TOOLS_ARGS
                        }
                    }

                    steps {
                        sh '''\
                            #!/bin/bash
                            set -ex

                            /home/tools/pull.sh

                            test/spatial/pull.sh

                            #test/spatial/test_spatial-ingestor.sh test-19-11-2021-11-50-point-marking-dta-canberra-kml
                            test/spatial/test_spatial-ingestor.sh test-19-11-2021-17-02-point-marking-dta-canberra-kmz
                            test/spatial/test_spatial-ingestor.sh test-16-11-202112-55-city-of-greater-bendigo-capital-works

                        '''.stripIndent()
                    }
                    post {
                        always {
                            junit 'test/spatial/.output/**/*.xml'
                            sh '''
                                rm -rf test/selenium/.logs test/selenium/.output
                            '''.stripIndent()
                        }
                    }
                }

                stage('CVE scan') {
                    when {
                        not { allOf { branch 'Staging'; branch 'Production' } }
                        beforeAgent true
                    }
                    agent {
                        docker {
                            image TOOLS_IMAGE
                            args TOOLS_ARGS
                        }
                    }

                    steps {
                        sh '''\
                            #!/bin/bash
                            set -e

                            /home/tools/cve-scan.sh
                        '''.stripIndent()
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'cve-scan.json', fingerprint: true
                        }
                    }
                }
            }
        }

        stage('Release') {
            when {
                branch 'Develop'
                beforeAgent true
            }
            agent {
                docker {
                    image TOOLS_IMAGE
                    args TOOLS_ARGS
                }
            }

            steps {
                withCredentials([sshUserPrivateKey(credentialsId: "GitHub-ssh", keyFileVariable: 'keyfile')]) {

                    sh '''
                        #!/bin/bash
                        set -e
                        mkdir -p ~/.ssh
                        ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
                        echo "Host github.com" > ~/.ssh/config
                        echo " HostName github.com" >> ~/.ssh/config
                        echo " IdentityFile ${keyfile}" >> ~/.ssh/config

                        git config --global user.email "pipeline@data.gov.au"
                        git config --global user.name "Jenkins"
                   
                        cd ${WORKSPACE}

                        #./build.sh --clean

                        #/home/tools/push.sh
                    '''.stripIndent()
                }
            }
        }
       
    }
}
