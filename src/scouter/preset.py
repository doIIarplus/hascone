"""MapleScouter manual preset v1, compatible with its public JSON importer."""
import copy

from scouter import profiles


def export(identifier):
    profile=profiles.load(identifier)
    data=copy.deepcopy(profiles.effective(profile))
    # The website accepts empty numeric strings, but rejects null values.
    for path,value in profiles.flatten(data).items():
        if value is None:
            if path=='hexa.hexaStat':
                raise ValueError('Choose the completed HEXA Stat core count before exporting.')
            profiles.assign(data,path,'')
    for source,target in {'restraintRing':'restraintRing','weaponRing':'weaponRing',
                          'continuosRing':'continuosRing','ringOfSum':'ringOfSum','riskTaker':'riskTakerRing'}.items():
        data['seedRing'][target]['level']=data['special'][source]
    return {'type':'maplescouter-manual-preset','v':1,'savedAt':profiles.now(),
            'label':profile['character']['name'][:40],'data':data}
