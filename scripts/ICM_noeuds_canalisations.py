"""
Model exported as python.
Name : Assignation des noeuds aux canalisations
Group : InfoWorks
With QGIS : 31601
"""

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsGeometry,
    QgsField,
    QgsFeatureRequest,
    QgsSpatialIndex,
    NULL,
)

from qgis.PyQt.QtCore import QVariant

import processing


class AssignationDesNoeudsAuxCanalisations(QgsProcessingAlgorithm):

    NODES = 'NODES'
    CANALISATIONS = 'CANALISATIONS'
    ATTRNODENAME = 'NODENAME'
    ATTRNODEZ = 'ATTRNODEZ'
    BUFFER = 'BUFFER'
    
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.CANALISATIONS,
                'Canalisations',
                types=[QgsProcessing.TypeVectorLine],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.NODES,
                'Noeuds',
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ATTRNODENAME,
                'Noeuds : Attribut de nom',
                type=QgsProcessingParameterField.Any,
                parentLayerParameterName=self.NODES,
                allowMultiple=False,
                defaultValue=''
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ATTRNODEZ,
                "Noeuds : Attribut d'altimétrie du radier",
                type=QgsProcessingParameterField.Any,
                parentLayerParameterName=self.NODES,
                allowMultiple=False,
                defaultValue=''
            )
        )
        param = QgsProcessingParameterNumber(
            self.BUFFER,
            'Buffer de recherche des noeuds aux extrémités des canalisations',
            type=QgsProcessingParameterNumber.Double,
            minValue=0.01,
            defaultValue=0.1,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def processAlgorithm(self, parameters, context, feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model

        layerNodes = self.parameterAsVectorLayer(parameters, self.NODES, context)
        layerCana = self.parameterAsVectorLayer(parameters, self.CANALISATIONS, context)
        attrNom = self.parameterAsString(parameters, self.ATTRNODENAME, context)
        attrZ = self.parameterAsString(parameters, self.ATTRNODEZ, context)
        buffer = self.parameterAsDouble(parameters, self.BUFFER, context)
        
        spatialIndexNodes = QgsSpatialIndex(layerNodes.getFeatures())
        
        total = 100.0 / layerCana.featureCount() if layerCana.featureCount() else 0
        
        feedback.setProgressText("Mise à jour des attributs des canalisations...")
        
        layerCana.startEditing()
        attrCana = list(layerCana.attributeAliases())
        
        if 'Noeud_am' not in attrCana:
            layerCana.addAttribute(QgsField('Noeud_am', QVariant.String))
        if 'Noeud_av' not in attrCana:
            layerCana.addAttribute(QgsField('Noeud_av', QVariant.String))
        if 'Radier_am' not in attrCana:
            layerCana.addAttribute(QgsField('Radier_am', QVariant.Double))
        if 'Radier_av' not in attrCana:
            layerCana.addAttribute(QgsField('Radier_av', QVariant.Double))
        
        layerCana.updateFields()
        feedback.setProgressText("Jointure des informations des noeuds aux canalisations...")
        
        warningMultipleNodes = False
        for current, featCana in enumerate(layerCana.getFeatures()):

            if feedback.isCanceled():
                break
            
            if featCana.geometry().isMultipart():
                if len(featCana.geometry().asMultiPolyline()[0]) > 2:
                    feedback.pushInfo('La canalisation {} contient un ou plusieurs sommet(s) intermédiaire(s).'.format(featCana.id()))
                canaNoeudAmont = QgsGeometry.fromPointXY(featCana.geometry().asMultiPolyline()[0][0])
                canaNoeudAval = QgsGeometry.fromPointXY(featCana.geometry().asMultiPolyline()[0][-1])
            else:
                if len(cana1.geometry().asPolyline()) > 2:
                    feedback.pushInfo('La canalisation {} contient un ou plusieurs sommet(s) intermédiaire(s).'.format(featCana.id()))
                canaNoeudAmont = QgsGeometry.fromPointXY(featCana.geometry().asPolyline()[0])
                canaNoeudAval = QgsGeometry.fromPointXY(featCana.geometry().asPolyline()[-1])
            
            searchBoxAmont = canaNoeudAmont.boundingBox()
            searchBoxAmont.grow(0.1)
            searchBoxAval = canaNoeudAval.boundingBox()
            searchBoxAval.grow(0.1)
            
            requestAmont = spatialIndexNodes.intersects(searchBoxAmont)
            requestAval = spatialIndexNodes.intersects(searchBoxAval)
            
            if len(requestAmont) != 1 or len(requestAval) != 1:
                if len(requestAmont) != 1:
                    feedback.pushInfo('{} noeud(s) trouvé(s) en amont de la canalisation {}. '.format(len(requestAmont), featCana.id()))
                    feedback.pushDebugInfo('requestAmont ids : ' + str(requestAmont))
                if len(requestAval) != 1:
                    feedback.pushInfo('{} noeud(s) trouvé(s) en aval de la canalisation {}. '.format(len(requestAval), featCana.id()))
                    feedback.pushDebugInfo('requestAval ids : ' + str(requestAval))
                warningMultipleNodes = True
                featCana['Noeud_am'] = NULL
                featCana['Radier_am'] = NULL
                featCana['Noeud_av'] = NULL
                featCana['Radier_av'] = NULL
                layerCana.updateFeature(featCana)
                continue
            
            nodeAmont = layerNodes.getFeature(requestAmont[0])
            nodeAval = layerNodes.getFeature(requestAval[0])
            
            featCana['Noeud_am'] = nodeAmont[attrNom]
            featCana['Radier_am'] = nodeAmont[attrZ]
            featCana['Noeud_av'] = nodeAval[attrNom]
            featCana['Radier_av'] = nodeAval[attrZ]
            layerCana.updateFeature(featCana)
            
            feedback.setProgress(int(current * total))
        
        layerCana.commitChanges()
        layerCana.rollBack()
        
        if warningMultipleNodes:
            feedback.reportError(
            """
            Attention !
            
            Aucun ou plusieurs noeuds ont été trouvés à l'une des extrémités d'une des canalisations !
            Voir le log ci-dessus.
            
            Vérifiez les géométries ou réduisez le buffer de recherche des noeuds.
            
            """
        )
        
        return {}

    def name(self):
        return 'ICM_noeuds_canalisations'

    def displayName(self):
        return 'Assignation des noeuds aux canalisations'

    def group(self):
        return 'InfoWorks'

    def groupId(self):
        return 'InfoWorks'
        
    def shortHelpString(self):
        return """
        Pre-Processing InfoWorks pour les réseaux pluviaux.
        
        Permet d'assigner, à chaque canalisation, le nom et le radier des noeuds amont et aval.
        
        Conseils : 
         - Utiliser l'accrochage lors de la création des lignes des canalisations.
        
        Limites : 
         - Il ne peut y avoir qu'un seul noeud aux extrémités des lignes.
         - Ne gère pas le cas où 2 canalisations démarrent ou arrivent à un noeud avec des radiers différents.
        """

    def createInstance(self):
        return AssignationDesNoeudsAuxCanalisations()
